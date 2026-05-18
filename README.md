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
For testing-
python -m nltk.downloader punkt stopwords

For Prod-

mkdir -p /data/arcaai/indumati/Projects/Akshayam/All_Newsletters/Newsletters/nltk_data
pip install nltk

python
>>> import nltk
>>> import sqlite3
nltk.download('stopwords', download_dir='/data/arcaai/indumati/Projects/Akshayam/All_Newsletters/Newsletters/nltk_data')
nltk.download('punkt', download_dir='/data/arcaai/indumati/Projects/Akshayam/All_Newsletters/Newsletters/nltk_data')
nltk.download('punkt_tab', download_dir='/data/arcaai/indumati/Projects/Akshayam/All_Newsletters/Newsletters/nltk_data')

Then in Python use:

import nltk

nltk.data.path.append(
    "/data/arcaai/indumati/Projects/Akshayam/All_Newsletters/Newsletters/nltk_data"
)

# Verify LangChain
python - <<EOF
import langchain
print(langchain.__version__)
from langchain.llms import Ollama
or 
from langchain_community.llms import Ollama
from langchain.prompts import PromptTemplate
or
from langchain_core.prompts import PromptTemplate
print("OK")
exit()

Run API:
python -m uvicorn api.main:app --reload

Run scheduler:
python scheduler/scheduler.py

Verify Tesseract:
tesseract --version