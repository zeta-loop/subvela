import os
import sys
from types import SimpleNamespace
from core.translator import Translator

# Ensure GEMINI_API_KEY is available (assuming it's in the environment already)
if not os.getenv('GEMINI_API_KEY'):
    print('Error: GEMINI_API_KEY not found in environment.')
    sys.exit(1)

terms_raw = """1|Kubernetes
2|Large Language Model
3|Subvela
4|Transformer architecture
5|React.js
6|Zero-shot learning
7|Fine-tuning
8|Reinforcement Learning from Human Feedback (RLHF)
9|Blockchain
10|Neuro-linguistic programming
11|Quantum Computing
12|Edge Computing
13|Serverless
14|API Gateway
15|CI/CD pipeline
16|GitOps
17|Infrastructure as Code (IaC)
18|Prompt Engineering
19|Context Window
20|Vector Database"""
entries = []
for line in terms_raw.strip().split('\n'):
    idx, text = line.split('|', 1)
    entries.append(SimpleNamespace(index=int(idx), original_text=text))

translator = Translator(provider='gemini', source_language='English')
results = {}

def on_complete(res):
    results.update(res)

def on_error(err):
    print(f'Error during translation: {err}')

print('Starting translation of specialized terms...')
# Using _translate_worker directly to avoid threading for simplicity in script
translator._translate_worker(entries, 'Chinese (Simplified)', None, on_complete, on_error)

print('\n--- Translation Results ---\n')
for entry in entries:
    orig = entry.original_text
    trans = results.get(entry.index, 'MISSING')
    status = 'TRANSLATED' if orig.lower() != trans.lower() else 'KEPT ORIGINAL'
    print(f'[{status}] {orig} -> {trans}')
