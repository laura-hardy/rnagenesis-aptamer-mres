# Base script for null sequence generation model 
# Will need to check before use and align with reference distribution requirements

import numpy as np
from collections import Counter

def get_corpus_stats(sequences):
    """Compute nucleotide frequencies and length distribution from corpus."""
    all_bases = "".join(sequences)
    counts = Counter(all_bases)
    total = sum(counts.values())
    freqs = {b: counts[b]/total for b in "ACUG"}
    lengths = [len(s) for s in sequences]
    return freqs, lengths

def generate_null_sequences(n, freqs, lengths, seed=42):
    rng = np.random.default_rng(seed)
    bases = list(freqs.keys())
    probs = [freqs[b] for b in bases]
    
    # Sample lengths from empirical distribution
    sampled_lengths = rng.choice(lengths, size=n, replace=True)
    
    sequences = []
    for length in sampled_lengths:
        seq = "".join(rng.choice(bases, size=length, p=probs))
        sequences.append(seq)
    
    return sequences