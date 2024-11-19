import os
import subprocess

if __name__ == "__main__":
    # Cambia "app.py" por el nombre de tu archivo principal de Streamlit
    subprocess.run(["streamlit", "run", "main.py", "--server.port", os.environ.get("PORT", "8501"), "--server.headless", "true"])