"""
Tool: transcribe_audio — Transcrição de áudio via OpenAI Whisper.
"""

import logging
import os

from openai import OpenAI, APIError, RateLimitError, APITimeoutError

from config.settings import settings
from config.agents import AGENT_CONFIGS

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = 25
UPLOAD_DIR = "temp_audios"


def transcribe_audio(file_path: str, agent_id: str) -> str:
    """
    Transcreve um arquivo de áudio usando OpenAI Whisper.

    O agent_id valida se o agente possui permissão para transcrição.
    Somente agentes com has_transcription=True podem usar esta ferramenta.

    Args:
        file_path: Caminho completo para o arquivo de áudio a ser transcrito.
        agent_id: Identificador do agente (ex: amorzito, auxiliar-medico).

    Returns:
        Texto transcrito ou mensagem de erro.
    """
    config = AGENT_CONFIGS.get(agent_id)
    if not config:
        return f"Erro: agente '{agent_id}' não registrado."

    if not config.get("has_transcription"):
        return f"Erro: agente '{agent_id}' não possui permissão para transcrição de áudio."

    # Validação do arquivo
    if not os.path.isfile(file_path):
        return f"Erro: arquivo não encontrado: {file_path}"

    allowed_extensions = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in allowed_extensions:
        return (
            f"Erro: formato de áudio '{ext}' não suportado. "
            f"Formatos aceitos: {', '.join(sorted(allowed_extensions))}"
        )

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        return (
            f"Erro: arquivo muito grande ({file_size_mb:.1f}MB). "
            f"O Whisper suporta no máximo {MAX_FILE_SIZE_MB}MB."
        )

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )

        if not transcript or not transcript.strip():
            return "Erro: Whisper retornou transcrição vazia."

        logger.info(
            f"transcribe_audio | agent={agent_id} | "
            f"chars={len(transcript)} | file={os.path.basename(file_path)}"
        )
        return f"Transcrição concluída com sucesso:\n\n{transcript.strip()}"

    except RateLimitError:
        return "Erro: limite de requisições excedido no Whisper. Tente novamente em alguns segundos."
    except APITimeoutError:
        return "Erro: a transcrição excedeu o tempo limite. Tente com um áudio menor."
    except APIError as e:
        logger.error(f"Erro na API OpenAI (Whisper): {e}")
        return f"Erro no serviço de transcrição: {e.message}"
    except Exception as e:
        logger.error(f"Erro na transcrição Whisper: {e}")
        return f"Erro: não foi possível transcrever o áudio: {str(e)}"
