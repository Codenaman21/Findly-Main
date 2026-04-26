
import requests
import logging

logger = logging.getLogger(__name__)

# Ollama local endpoint
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:1.5b"

# Timeout settings (seconds)
REQUEST_TIMEOUT = 60


def query_llm(prompt: str, temperature: float = 0.2) -> str:
    """
    Send a prompt to the local Ollama instance and return the response text.

    Args:
        prompt: The full prompt string to send.
        temperature: Controls randomness (lower = more deterministic).

    Returns:
        The model's response as a string, or an error fallback string.
    """
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 150,# Max tokens in response
            "top_p": 0.9,              # optional stability
            "repeat_penalty": 1.1,
            "stop": ["\n\n"]
        }
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()

        data = response.json()
        result = data.get("response", "").strip()

        if not result:
            logger.warning("LLM returned empty response")
            return '{"error": "Empty response from LLM"}'

        logger.info(f"LLM responded ({len(result)} chars)")
        return result

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to Ollama. Is it running on localhost:11434?")
        return '{"error": "LLM service unavailable. Ensure Ollama is running."}'

    except requests.exceptions.Timeout:
        logger.error(f"Ollama request timed out after {REQUEST_TIMEOUT}s")
        return '{"error": "LLM request timed out"}'

    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama request failed: {e}")
        return '{"error": "LLM request failed"}'

    except Exception as e:
        logger.error(f"Unexpected error querying LLM: {e}")
        return '{"error": "Unexpected LLM error"}'


def check_health() -> bool:
    """Check if Ollama is reachable and the model is loaded."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        available = any(MODEL_NAME in name for name in model_names)
        if not available:
            logger.warning(f"Model '{MODEL_NAME}' not found. Available: {model_names}")
        return available
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        return False
