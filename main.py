import streamlit as st
import pandas as pd
import requests
from decouple import config

TOKEN = config("TOKEN")
CANVAS_API_URL = 'https://canvas.uautonoma.cl/api/v1'
HEADERS = {
    'Authorization': f'Bearer {TOKEN}'
}

