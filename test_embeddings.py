"""
Scratch script -- tests whether nomic-embed-text places related tax notes
(different terminology, same underlying framework) close together in vector
space. Not part of the app. Run with: python test_embeddings.py
"""

import math

from dotenv import load_dotenv

load_dotenv()

from embeddings import get_embedding  # noqa: E402 -- must follow load_dotenv()


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b)


notes = {
    "FATCA": "FATCA requires foreign financial institutions to report US account holders to the IRS or face 30% withholding on US-source payments.",
    "Chapter 4": "Chapter 4 of the Internal Revenue Code contains the FATCA withholding and reporting rules for payments to foreign entities.",
    "Section 1.1471-6": "Treasury Regulation section 1.1471-6 lists categories of payments exempt from Chapter 4 withholding, such as certain grandfathered obligations.",
    "General withholding": "US withholding tax and information reporting rules require payers to withhold tax on certain payments to foreign persons and report those payments to the IRS.",
    "Unrelated baseline": "The recipe calls for two cups of flour, a teaspoon of baking soda, and butter softened at room temperature.",
}

print("Computing embeddings...")
embeddings = {name: get_embedding(text) for name, text in notes.items()}

print("\nPairwise similarity (higher = closer):")
names = list(embeddings.keys())
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        sim = cosine_similarity(embeddings[names[i]], embeddings[names[j]])
        print(f"  {names[i]} <-> {names[j]}: {sim:.3f}")