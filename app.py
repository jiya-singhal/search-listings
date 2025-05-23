# -*- coding: utf-8 -*-

# streamlit_app.py

import streamlit as st
from sentence_transformers import SentenceTransformer
from fuzzywuzzy import fuzz
import numpy as np
import pandas as pd
import faiss

# Streamlit page setup
st.set_page_config(page_title="Smart Product Search", page_icon="🛍️", layout="centered")

# Load model once and cache
@st.cache_resource
def load_model():
    return SentenceTransformer('all-mpnet-base-v2')

model = load_model()

# Load products from CSV and cache
@st.cache_data
def load_products(csv_path="cleaned_products.csv"):
    df = pd.read_csv(
        csv_path,
        encoding='latin1'
    )
    
    if "name" not in df.columns:
        st.error("CSV must have a 'name' column.")
        st.stop()
    return df["name"].dropna().astype(str).tolist()

products = load_products()

# Build FAISS index and cache
@st.cache_resource
def build_faiss_index(products_list):
    embeddings = model.encode(products_list, convert_to_numpy=True, show_progress_bar=True)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    return index, embeddings

faiss_index, product_embeddings = build_faiss_index(products)

# Functions
def preprocess_query(query):
    """Lowercase, strip, and remove stop words."""
    stop_words = set(["the", "a", "an", "of", "and", "in", "for", "on", "with", "to"])
    words = query.lower().split()
    query_clean = " ".join([word for word in words if word not in stop_words])
    return query_clean

def get_fuzzy_scores(query_clean, indices):
    """Compute fuzzy matching scores for selected candidates."""
    fuzzy_scores = [fuzz.token_set_ratio(query_clean, products[i].lower()) / 100 for i in indices]
    
    # Check for partial substring match and boost the score if there's a match
    substring_boost = [1.0 if query_clean in products[i].lower() else 0.0 for i in indices]
    
    return fuzzy_scores, substring_boost



def search_products(query, top_k=10):
    query_clean = preprocess_query(query)
    query_embedding = model.encode([query_clean], convert_to_numpy=True)

    distances, indices = faiss_index.search(query_embedding, top_k * 3)  # Search top 30 initially
    ai_scores = 1 - distances[0]  # Convert L2 distance to cosine similarity

    fuzzy_scores, substring_boost = get_fuzzy_scores(query_clean, indices[0])

    startswith_boost = [1.0 if products[i].lower().startswith(query_clean) else 0.0 for i in indices[0]]

    # Final scoring, with weights adjusted for AI, fuzzy, startswith, and substring boosts
    final_scores = (
        np.array(0.4) * np.array(ai_scores) +  # Reduced AI weight
        np.array(0.4) * np.array(fuzzy_scores) +  # Reduced fuzzy match weight
        np.array(0.1) * np.array(startswith_boost) +  # Low weight on startswith
        np.array(0.1) * np.array(substring_boost)  # Boost for partial matches
    )

    # Filter results with low scores (only keep results above 10% match)
    final_scores = np.array(final_scores)
    filtered_indices = np.where(final_scores > 0.1)[0]  # Only keep results above 10%
    top_k_indices = filtered_indices[np.argsort(-final_scores[filtered_indices])][:top_k]

    return [(products[indices[0][i]], final_scores[i]) for i in top_k_indices]


# Streamlit App Frontend
st.title("🛍️ Smart Product Search (AI + Fuzzy Matching)")

query = st.text_input("🔍 Type a product name:", placeholder="e.g., green tea, stabilizer, jeans...")

if query:
    with st.spinner('Searching...'):
        results = search_products(query)
    
    if len(results) == 0:
        st.warning("No relevant matches found.")
    else:
        st.subheader("Top Matches:")
        for name, score in results:
            st.write(f"🔹 **{name}** — {score * 100:.2f}% match")
else:
    st.info("Enter a product name to start searching!")
