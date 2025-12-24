"""Production-ready script to run the FastAPI server."""
import os
import sys
import socket
import logging
import uvicorn
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to Python path so we can import app
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

# Configure logging early
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def is_port_available(host: str, port: int) -> bool:
    """Check if a port is available by trying to bind to it."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False
    except Exception:
        return False


if __name__ == "__main__":
    # Production settings
    is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
    
    # Get host and port from environment
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8009"))
    
    # Check if port is available
    if not is_port_available(host, port):
        print(f"ERROR: Port {port} is already in use!")
        print(f"\nTo fix this, you can:")
        print(f"1. Stop the process using port {port}")
        print(f"2. Use a different port by setting API_PORT environment variable")
        print(f"3. On Windows, find and kill the process:")
        print(f"   netstat -ano | findstr :{port}")
        print(f"   taskkill /PID <PID> /F")
        sys.exit(1)
    
    # Determine loop type - uvloop doesn't work on Windows
    loop_type = "auto"
    if not is_production and sys.platform != "win32":
        # Try to use uvloop on Unix systems if available
        try:
            import uvloop
            loop_type = "uvloop"
        except ImportError:
            loop_type = "auto"
    
    print(f"Starting FastAPI server on http://{host}:{port}")
    print(f"API Documentation: http://{host}:{port}/docs")
    print(f"Health Check: http://{host}:{port}/health")
    
    try:
        # Production concurrency settings
        workers = int(os.getenv("WORKERS", "4")) if is_production else 1
        max_concurrent = int(os.getenv("MAX_CONCURRENT", "100"))
        keep_alive = int(os.getenv("KEEP_ALIVE", "120"))  # Keep-alive timeout (2 minutes)
        timeout = int(os.getenv("TIMEOUT", "120"))  # Request timeout in seconds (2 minutes)
        backlog = int(os.getenv("BACKLOG", "2048"))  # Socket backlog
        
        logger.info(f"Starting server with {workers} worker(s), max_concurrent={max_concurrent}")
        logger.info(f"Production mode: {is_production}")
        logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
        
        # Production-optimized uvicorn configuration
        uvicorn.run(
            "app:app",
            host=host,
            port=port,
            reload=not is_production and os.getenv("API_RELOAD", "false").lower() == "true",
            log_level=os.getenv("LOG_LEVEL", "info").lower(),
            workers=workers if is_production else 1,  # Single worker in dev for debugging
            access_log=not is_production,  # Disable access logs in production for performance
            loop=loop_type,
            limit_concurrency=max_concurrent,  # Max concurrent connections
            timeout_keep_alive=keep_alive,  # Keep-alive timeout (2 minutes)
            timeout_graceful_shutdown=timeout,  # Graceful shutdown timeout (2 minutes)
            backlog=backlog,  # Socket backlog for better connection handling
            server_header=False,  # Security: Don't expose server version
            # Production optimizations
            limit_max_requests=1000 if is_production else None,  # Restart workers after N requests (prevents memory leaks)
            limit_max_requests_jitter=50 if is_production else None,  # Jitter to prevent thundering herd
        )
    except OSError as e:
        if "10048" in str(e) or "address already in use" in str(e).lower():
            print(f"\nERROR: Port {port} is already in use!")
            print(f"\nTo fix this:")
            print(f"1. Stop any other FastAPI/uvicorn processes")
            print(f"2. Use a different port: API_PORT=8009 uv run python scripts/run_api.py")
            print(f"3. On Windows, find the process:")
            print(f"   netstat -ano | findstr :{port}")
        else:
            print(f"\n❌ ERROR: {e}")
        sys.exit(1)

