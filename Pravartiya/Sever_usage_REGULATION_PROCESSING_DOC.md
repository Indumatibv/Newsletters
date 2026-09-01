# Regulation Processing Architecture and Capacity Notes

This note is based on the actual processing code in the project, especially:
- `Pravartiya/agents/SEBI_Regulations/Extract_Chunks_1.py`
- `Pravartiya/agents/SEBI_Regulations/Summary_all_5.py`
- `Pravartiya/agents/SEBI_other_subdomains/SEBI_circulars.py`
- `Pravartiya/agents/Parsing_agent.py`

## 1) Models used

### Regulation processing
The regulation pipeline currently uses:
- Ollama model: `mistral:latest`
- Called via HTTP POST to `http://localhost:11434/api/generate`
- The model is configured in the summary generation flow in `Summary_all_5.py`

Evidence in the repo:
- `llm = Ollama(model="mistral:latest")` in circular-related processing files
- `payload = { "model": "mistral:latest", ... }` in summary generation

### Other document types
For circulars, consultation papers, press releases, informal guidance, and NSE/BSE circulars, the same local Ollama model is used (`mistral:latest`).

### Model class
This is a local Mistral-class LLM, not a custom fine-tuned model. In practice, it behaves like a 7B-class local model depending on the exact model package and quantization used by Ollama.

---

## 2) PDF parsing libraries used

### For regulation PDFs
The actual regulation flow uses:
- `pdfplumber`

Code path:
- `with pdfplumber.open(pdf_path) as pdf:`
- `text = page.extract_text()`
- optional page crop logic based on footer separator lines

This is the main extraction mechanism in `Extract_Chunks_1.py`.

### For non-regulation PDF documents
Some of the other document types use:
- `unstructured.partition.pdf`
- strategy values: `fast` and `hi_res`

This is in the circular processing file, where `partition_pdf(...)` is used for extraction before sending content to the LLM.

### Summary
- Regulation PDFs: `pdfplumber`
- Other PDFs: `unstructured.partition.pdf` + `pdfplumber` in some flows
- OCR libraries such as `unstructured.pytesseract` and `google-cloud-vision` are present in dependencies, but they are not the active path that is clearly wired into the current regulation extraction flow.

---

## 3) Input size for LLM per chunk and per PDF

### Chunk-level input size
The prompt payload is built from a target legal clause or context. In the code, the LLM call uses large text snippets such as:
- `text[:10000]`
- `text[:12000]`

This means the per-call input is usually capped around:
- around 10,000 to 12,000 characters per prompt for the smaller summary calls

This is not arbitrary; it is explicitly passed in the code for prompt context:
- `GIST_PROMPT.format(text=text[:10000])`
- `ACTION_POINT_PROMPT.format(text=text[:10000])`
- `NSE_BSE_CIRCULAR_PROMPT.format(text=text[:12000], ...)`

### Overall PDF input size to the LLM
For a full regulation PDF, the model is not fed the entire PDF in one shot. Instead, it gets selected chunks and filtered context, for example:
- target footer text
- mapped regulation chunks
- relevant clause excerpts

This is the pattern in `generate_summary_for_footer()` in `Summary_all_5.py`:
- extracts the target footnote text
- gathers mapped regulation chunks
- builds a filtered context from the relevant clause text
- sends only that filtered context to the model

So in production, the total LLM input per PDF is best thought of as:
- several chunk-level prompts, each typically 5k–12k characters
- aggregated across all mapped footnotes / clauses in that PDF

### Practical estimate
For a regulation PDF with moderate length:
- per chunk prompt: 5k–12k characters
- per PDF total prompt volume: often 50k–300k+ characters, depending on clause count and document complexity

This is still manageable for a local Mistral-class model, but it is not a single giant prompt; it is a multi-chunk sequential prompting process.

---

## 4) Output size per chunk and per PDF

### Per chunk output size
The model output is meant to be compact and structured. The prompt requires a strict output format with 4 fixed fields:
- `Regulation Number:`
- `Gist of amendment:`
- `Existing provisions of Law prior to amendment:`
- `Action point for listed entity if any:`

This means the output is usually short and structured, often in the range of:
- a few hundred to a few thousand characters per chunk

### Per PDF output size
For a regulation PDF, multiple footnotes/clauses may be processed. The project loops through all mapped footnotes in `process_all_footers()` and calls the LLM for each one:
- `for footer_id, payload in mapped_data.items(): ... summary = generate_summary_for_footer(...)`

So the overall output is the sum of all generated summaries for that PDF. A realistic total is:
- low MB range for a normal PDF
- higher if the PDF has many mapped footnotes or many clause-level summaries

### Reasonable estimate
For one regulation PDF:
- extracted raw text: roughly 0.2 MB to 1.5 MB depending on page count and legal density
- chunked/structured output: roughly 0.3 MB to 2.0 MB
- final model summary output: usually much smaller than the extracted raw text, often tens of KB to a few hundred KB, depending on number of summaries

A practical production estimate for a normal regulation PDF is:
- total output generated per PDF: about 0.5 MB to 2.5 MB

---

## 5) Max GPU needed for processing one regulation PDF in production

### Important point
The PDF extraction stage (`pdfplumber`) is CPU-bound and does not use CUDA.
The GPU matters mainly for the model inference stage.

For a local Mistral-class model such as `mistral:latest` in Ollama, a practical production estimate is:
- 6 GB VRAM: minimum workable for smaller cases
- 8 GB VRAM: safer and more stable for one PDF end-to-end
- 12 GB VRAM: comfortable for larger PDFs or moderate concurrency
- 16–24 GB VRAM: recommended if multiple PDFs are processed in parallel or if the system does concurrent local inference

### Best estimate for one production PDF
For a single regulation PDF end-to-end, a good target is:
- 8 GB VRAM as the realistic production minimum
- 12 GB VRAM as the safer recommended configuration

This is not because `pdfplumber` needs GPU; it is because the LLM inference, prompt processing, and real-time local model execution do.

---

## 6) How many LLM calls per PDF

The code clearly does not do one single LLM call per PDF.
It loops over footnotes/entries and calls the model per mapped footer/clause summary.

Evidence in `Summary_all_5.py`:
- `process_all_footers(mapped_data)` loops through all footer entries
- for each footer it does `summary = generate_summary_for_footer(...)`
- the summary function itself performs the model call

So the number of LLM calls is roughly:
- one call per mapped footnote / clause summary

### Typical estimate
For one regulation PDF:
- a small PDF may do 1–5 LLM calls
- a moderate PDF may do 5–20 calls
- a large PDF with many footnotes or mapped sections may do 20–50+ calls

This is why server capacity matters: the total cost is not just one model invocation, but many sequential calls across the document.

---

## 7) Why we need a server instead of a local system, even though pdfplumber does not use GPU

### The answer is simple
The pipeline is not only `pdfplumber`.
It is a full end-to-end legal processing pipeline with multiple stages:
- PDF extraction
- page cleanup and footer removal
- section/chunk generation
- mapping of legal clauses and footnotes
- multiple LLM prompts
- structured output generation
- long-running batch processing

This workload is CPU-heavy, memory-heavy, and often long-running.

### Why a server is better than a local laptop
Even without CUDA, a server is preferable because it gives:
- more CPU cores for PDF parsing and text cleanup
- more RAM for chunk processing and prompt context
- faster SSD storage and less I/O bottleneck
- fewer competing processes
- stable performance for long-running jobs
- ability to process multiple PDFs without user interruption
- consistent availability for batch jobs and background processing

### Very important point
`pdfplumber` is not GPU-dependent, but the overall system is still not a lightweight local task. The LLM stage is the main GPU-relevant part, but the extraction stage is still expensive in CPU and RAM. So a server is needed for both reasons:
- CPU-heavy document processing
- local LLM inference and batch processing

---

## 8) Bottom line

For the current repo, the regulation pipeline is best described as:
- PDF parsing via `pdfplumber`
- legal chunking and mapping logic
- local LLM inference via Ollama `mistral:latest`
- multiple model calls per PDF
- server needed because the workload is multi-stage, resource-heavy, and runs in batches

### Production sizing guidance
- For one regulation PDF: target 8 GB VRAM minimum, 12 GB safer
- For parallel batch processing: 16–24 GB VRAM recommended
- The output per PDF is roughly 0.5–2.5 MB combined, depending on page count and number of mapped clauses
- LLM calls per PDF are usually multiple, not one, and scale with the number of footnotes / mapped sections

This is the practical capacity model for the existing project architecture.
