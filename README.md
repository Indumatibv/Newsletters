# Newsletters
python3.10 -m venv Akshayam
source Akshayam/bin/activate
deactivate
rm -rf Akshayam

# Install dependencies
python -m pip install -r requirements.txt
python -m pip install "unstructured[all-docs]" nltk

# Install Playwright browsers
python -m playwright install

# (Optional) NLTK data
python -m nltk.downloader punkt stopwords

# Verify LangChain
python - <<EOF
import langchain
print(langchain.__version__)
from langchain.llms import Ollama
from langchain.prompts import PromptTemplate
print("OK")
EOF

Run API:
python -m uvicorn api.main:app --reload

Run scheduler:
python scheduler/scheduler.py

Verify Tesseract:
tesseract --version