from flask import Flask, render_template, request, flash, redirect, url_for, session, make_response, jsonify
from flask_session import Session
import os
from dotenv import load_dotenv
import pymupdf
import requests
from werkzeug.utils import secure_filename
import logging
from langchain.text_splitter import CharacterTextSplitter
from fpdf import FPDF
import time
import random
import json
from json_repair import repair_json
import pytesseract
from PIL import Image
import io

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'Uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

def extract_text_from_pdf(file_path):
    try:
        doc = pymupdf.open(file_path)
        text = ""
        for page in doc:
            page_text = page.get_text()
            if len(page_text.strip()) < 50:  # If little text, try OCR
                logger.debug(f"Low text content on page {page.number}, attempting OCR...")
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes()))
                ocr_text = pytesseract.image_to_string(img, lang='eng')
                text += ocr_text + "\n"
            else:
                text += page_text + "\n"
        doc.close()
        if not text.strip():
            return None, "No text extracted from PDF, even with OCR."
        logger.debug(f"Extracted PDF text (length: {len(text)}): {text[:200]}...")
        return text, None
    except Exception as e:
        logger.error(f"PDF extraction failed: {str(e)}")
        return None, str(e)

def get_summary_from_groq(text, summary_length="medium", summary_format="structured"):
    try:
        # Define max tokens based on summary length
        max_tokens = {"short": 100, "medium": 300, "detailed": 500}.get(summary_length, 300)
        
        # Split text into chunks
        splitter = CharacterTextSplitter(chunk_size=3000, chunk_overlap=200, separator="\n")
        chunks = splitter.split_text(text)
        logger.debug(f"Split text into {len(chunks)} chunks")
        
        chunk_summaries = []
        key_points = []
        for i, chunk in enumerate(chunks):
            for attempt in range(3):  # Retry up to 3 times for rate limits
                try:
                    logger.debug(f"Processing chunk {i+1}/{len(chunks)} (length: {len(chunk)})")
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    chunk_prompt = (
                        f"Summarize the following text in 1-2 sentences and provide 2-3 key points as bullet points. "
                        f"Return only a JSON object with keys 'summary' (string) and 'key_points' (array of strings), "
                        f"without any introductory phrases or metadata:\n\n{chunk}"
                    )
                    data = {
                        "model": "llama3-8b-8192",
                        "messages": [{"role": "user", "content": chunk_prompt}],
                        "max_tokens": 200,
                        "temperature": 0.7
                    }
                    response = requests.post(url, headers=headers, json=data)
                    response.raise_for_status()
                    result = response.json()['choices'][0]['message']['content'].strip()
                    
                    # Repair JSON if malformed
                    try:
                        result_json = json.loads(result)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Malformed JSON in chunk {i+1}: {str(e)}, attempting repair...")
                        result = repair_json(result, skip_json_loads=True)
                        try:
                            result_json = json.loads(result)
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON repair failed for chunk {i+1}: {str(e)}")
                            if attempt < 2:
                                wait_time = (2 ** attempt) + random.uniform(0, 0.1)
                                logger.warning(f"Retrying chunk {i+1} in {wait_time}s...")
                                time.sleep(wait_time)
                                continue
                            return None, f"Failed to parse JSON for chunk {i+1}: {str(e)}"
                    
                    # Validate JSON structure
                    if not isinstance(result_json, dict) or 'summary' not in result_json or 'key_points' not in result_json:
                        logger.error(f"Invalid JSON structure for chunk {i+1}: {result_json}")
                        if attempt < 2:
                            wait_time = (2 ** attempt) + random.uniform(0, 0.1)
                            logger.warning(f"Retrying chunk {i+1} in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        return None, f"Invalid JSON structure for chunk {i+1}"
                    
                    chunk_summaries.append(result_json['summary'])
                    key_points.extend(result_json['key_points'])
                    logger.debug(f"Chunk {i+1} summary: {result_json['summary']}, Key points: {result_json['key_points']}")
                    break
                except requests.RequestException as e:
                    if attempt < 2:
                        wait_time = (2 ** attempt) + random.uniform(0, 0.1)
                        logger.warning(f"API request failed for chunk {i+1}: {str(e)}, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    logger.error(f"Summary API request failed for chunk {i+1}: {str(e)}")
                    return None, f"Failed to summarize chunk {i+1}: {str(e)}"
        
        if not chunk_summaries:
            return None, "No summaries generated: empty response from API"
        
        # Combine summaries and key points
        combined_text = "\n\n".join(chunk_summaries)
        unique_key_points = list(dict.fromkeys(key_points))[:10]  # Limit to 10 unique key points
        
        # Define final prompt based on format
        if summary_format == "paragraph":
            final_prompt = (
                f"Generate a {summary_length} summary (approximately {max_tokens} tokens) of the following text in paragraph form. "
                f"Return only the summary text without introductory phrases or metadata:\n\n{combined_text}"
            )
        elif summary_format == "bullet_points":
            final_prompt = (
                f"Generate a {summary_length} summary (approximately {max_tokens} tokens) of the following text as 5-10 bullet points. "
                f"Return only a JSON array of strings without introductory phrases or metadata:\n\n{combined_text}"
            )
        else:  # structured
            final_prompt = (
                f"Generate a detailed summary of the following text with four sections: "
                f"1. Overview (2-3 sentences summarizing the main content), "
                f"2. Key Points (5-10 bullet points based on the provided points), "
                f"3. Themes (1-2 sentences identifying recurring topics), "
                f"4. Conclusion (1-2 sentences on significance or findings). "
                f"Return only a JSON object with keys 'overview' (string), 'key_points' (array of strings), "
                f"'themes' (string), and 'conclusion' (string), without introductory phrases or metadata:\n\n"
                f"{combined_text}\n\nKey Points:\n{json.dumps(unique_key_points)}"
            )
        
        for attempt in range(3):  # Retry for final summary
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": "llama3-8b-8192",
                    "messages": [{"role": "user", "content": final_prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.7
                }
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()['choices'][0]['message']['content'].strip()
                
                if summary_format == "bullet_points":
                    try:
                        final_summary = json.loads(result)
                        if not isinstance(final_summary, list):
                            raise ValueError("Expected JSON array for bullet points")
                        return {"overview": "", "key_points": final_summary, "themes": "", "conclusion": ""}, None
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Malformed JSON for bullet points: {str(e)}, attempting repair...")
                        result = repair_json(result, skip_json_loads=True)
                        try:
                            final_summary = json.loads(result)
                            if not isinstance(final_summary, list):
                                raise ValueError("Expected JSON array for bullet points")
                            return {"overview": "", "key_points": final_summary, "themes": "", "conclusion": ""}, None
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.error(f"JSON repair failed for bullet points: {str(e)}")
                            if attempt < 2:
                                continue
                            return {
                                "overview": "",
                                "key_points": unique_key_points or ["No key points identified."],
                                "themes": "",
                                "conclusion": ""
                            }, None
                elif summary_format == "paragraph":
                    return {
                        "overview": result,
                        "key_points": [],
                        "themes": "",
                        "conclusion": ""
                    }, None
                else:  # structured
                    try:
                        final_summary_json = json.loads(result)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Malformed JSON in final summary: {str(e)}, attempting repair...")
                        result = repair_json(result, skip_json_loads=True)
                        try:
                            final_summary_json = json.loads(result)
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON repair failed for final summary: {str(e)}")
                            if attempt < 2:
                                wait_time = (2 ** attempt) + random.uniform(0, 0.1)
                                logger.warning(f"Retrying final summary in {wait_time}s...")
                                time.sleep(wait_time)
                                continue
                            return {
                                "overview": combined_text[:500] + "..." if len(combined_text) > 500 else combined_text,
                                "key_points": unique_key_points or ["No key points identified."],
                                "themes": "No recurring themes identified due to processing error.",
                                "conclusion": "The document could not be fully summarized due to processing limitations."
                            }, None
                
                    # Validate final summary structure
                    required_keys = ['overview', 'key_points', 'themes', 'conclusion']
                    if not isinstance(final_summary_json, dict) or not all(key in final_summary_json for key in required_keys):
                        logger.error(f"Invalid final summary structure: {final_summary_json}")
                        if attempt < 2:
                            wait_time = (2 ** attempt) + random.uniform(0, 0.1)
                            logger.warning(f"Retrying final summary in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        return {
                            "overview": combined_text[:500] + "..." if len(combined_text) > 500 else combined_text,
                            "key_points": unique_key_points or ["No key points identified."],
                            "themes": "No recurring themes identified due to processing error.",
                            "conclusion": "The document could not be fully summarized due to processing limitations."
                        }, None
                
                    # Ensure non-empty fields
                    final_summary_json['overview'] = final_summary_json['overview'] or "No overview generated."
                    final_summary_json['key_points'] = final_summary_json['key_points'] or ["No key points identified."]
                    final_summary_json['themes'] = final_summary_json['themes'] or "No recurring themes identified."
                    final_summary_json['conclusion'] = final_summary_json['conclusion'] or "No conclusion generated."
                
                    logger.debug(f"Final structured summary: {json.dumps(final_summary_json, indent=2)}")
                    return final_summary_json, None
            except requests.RequestException as e:
                if attempt < 2:
                    wait_time = (2 ** attempt) + random.uniform(0, 0.1)
                    logger.warning(f"Final summary API request failed: {str(e)}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Final summary API request failed: {str(e)}")
                return {
                    "overview": combined_text[:500] + "..." if len(combined_text) > 500 else combined_text,
                    "key_points": unique_key_points or ["No key points identified."],
                    "themes": "No recurring themes identified due to processing error.",
                    "conclusion": "The document could not be fully summarized due to processing limitations."
                }, None
    except Exception as e:
        logger.error(f"Summary processing failed: {str(e)}")
        return None, str(e)

def get_chat_response(question, pdf_text):
    try:
        # Split text into chunks for context
        splitter = CharacterTextSplitter(chunk_size=3000, chunk_overlap=200, separator="\n")
        chunks = splitter.split_text(pdf_text)
        relevant_chunks = chunks[:3]  # Limit to first 3 chunks to stay within token limits
        context = "\n\n".join(relevant_chunks)
        
        for attempt in range(3):
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": "llama3-8b-8192",
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Answer the following question based on the provided PDF content. "
                                f"Return only the answer text without introductory phrases:\n\n"
                                f"PDF Content:\n{context}\n\nQuestion: {question}"
                            )
                        }
                    ],
                    "max_tokens": 200,
                    "temperature": 0.7
                }
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                answer = response.json()['choices'][0]['message']['content'].strip()
                logger.debug(f"Chat response for question '{question}': {answer}")
                return answer, None
            except requests.RequestException as e:
                if attempt < 2:
                    wait_time = (2 ** attempt) + random.uniform(0, 0.1)
                    logger.warning(f"Chat API request failed: {str(e)}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"Chat API request failed: {str(e)}")
                return None, f"Failed to process question: {str(e)}"
    except Exception as e:
        logger.error(f"Chat processing failed: {str(e)}")
        return None, str(e)

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected.', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(request.url)
        
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Get summary options
            summary_length = request.form.get('summary_length', 'medium')
            summary_format = request.form.get('summary_format', 'structured')
            
            # Extract text
            text, error = extract_text_from_pdf(file_path)
            if text is None:
                flash(f'Error processing PDF: {error}', 'error')
                os.remove(file_path)
                return redirect(request.url)
            
            # Get summary
            summary, error = get_summary_from_groq(text, summary_length, summary_format)
            if summary is None:
                flash(f'Error generating summary: {error}', 'error')
                os.remove(file_path)
                return redirect(request.url)
            
            # Store summary and PDF text in session
            session['summary'] = summary
            session['summary_format'] = summary_format
            session['pdf_text'] = text
            
            # Clean up
            os.remove(file_path)
            return render_template('result.html', summary=summary, summary_format=summary_format)
        
        flash('Please upload a valid PDF file.', 'error')
        return redirect(request.url)
    
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    question = request.form.get('question')
    pdf_text = session.get('pdf_text', '')
    if not question or not pdf_text:
        return jsonify({'error': 'No question or PDF content available.'}), 400
    
    answer, error = get_chat_response(question, pdf_text)
    if error:
        return jsonify({'error': error}), 500
    return jsonify({'answer': answer})

@app.route('/download_summary', methods=['GET'])
def download_summary():
    summary = session.get('summary', {'overview': 'No summary available', 'key_points': [], 'themes': '', 'conclusion': ''})
    summary_format = session.get('summary_format', 'structured')
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "Summary", ln=True, align='C')
    pdf.ln(5)
    
    if summary_format == "paragraph":
        pdf.multi_cell(0, 10, summary['overview'])
    elif summary_format == "bullet_points":
        for point in summary['key_points']:
            pdf.multi_cell(0, 10, f"- {point}")
    else:  # structured
        pdf.cell(0, 10, "Overview", ln=True)
        pdf.multi_cell(0, 10, summary['overview'])
        pdf.ln(5)
        pdf.cell(0, 10, "Key Points", ln=True)
        for point in summary['key_points']:
            pdf.multi_cell(0, 10, f"- {point}")
        pdf.ln(5)
        pdf.cell(0, 10, "Themes", ln=True)
        pdf.multi_cell(0, 10, summary['themes'])
        pdf.ln(5)
        pdf.cell(0, 10, "Conclusion", ln=True)
        pdf.multi_cell(0, 10, summary['conclusion'])
    
    pdf_output = pdf.output(dest='S').encode('latin1')
    response = make_response(pdf_output)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=summary.pdf'
    return response

if __name__ == '__main__':
    app.run(debug=True)