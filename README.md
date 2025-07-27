# PDF Summarizer Web App

A Flask-based web application that allows users to upload PDF files and get AI-generated summaries in various formats: **overview**, **bullet points**, **structured summaries**, and a **chat interface** to ask questions based on the document. The app also supports **theme toggling**, **OCR fallback for scanned PDFs**, and **downloadable summaries in PDF format**.

## Sample Image 1

![image alt](https://github.com/shahil5z/TalkToPDF/blob/e9b0e3994e809dcca7f5153fbc5263aaceb85cb4/SampleImage/1.png)

## Sample Image 2

![image alt](https://github.com/shahil5z/TalkToPDF/blob/e9b0e3994e809dcca7f5153fbc5263aaceb85cb4/SampleImage/2.png)

---

## 🚀 Features

-  **Upload any PDF** and extract text automatically
-  **Choose summary type**: Overview, Bullet Points, Structured
-  **Chat with your PDF** using context-aware AI
-  **Dark/Light mode** toggle with persistent preference
-  **Download the summary** as a PDF
-  **Automatic retry with exponential backoff** for API failures
-  **Clean and intuitive UI** using Bootstrap
-  **OCR support** for image-based or scanned PDFs

---

##  Tech Stack

- **Backend**: Python, Flask
- **Frontend**: HTML, CSS, JavaScript (Bootstrap)
- **PDF Processing**: PyMuPDF, pytesseract, PIL
- **AI Summarization**: GROQ API
- **PDF Generation**: FPDF
