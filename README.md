# Breathe ESG Platform

Enterprise ESG emissions ingestion and analyst review platform.

## Stack
- Django REST Framework
- React + Vite
- PostgreSQL
- TailwindCSS

## Features
- SAP ingestion
- Utility electricity ingestion
- Corporate travel ingestion
- Scope 1/2/3 normalization
- Audit logs
- Analyst dashboard
- Suspicious record detection
- Approve/reject workflow

## Run Backend

```bash
cd backend
pip install -r requirements.txt
python manage.py runserver
```

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```