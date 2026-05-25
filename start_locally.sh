#!/bin/bash
#
source ../myenv/bin/activate

cd backend && uvicorn app.main:app --reload --port 8000

