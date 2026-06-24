"""Count character dictionary size"""
import yaml

# Load YAML
with open(r'c:\Software\screen_translate\PP-OCRv5_mobile_rec_infer\inference.yml', 'r', encoding='utf-8') as f:
    d = yaml.safe_load(f)

chars = d['PostProcess']['character_dict']
print(f"YAML character_dict size: {len(chars)}")

# The model output should be len(chars) + 1 for CTC blank
# Or len(chars) + 2 for some models
expected_vocab = len(chars) + 1
print(f"Expected vocab size (chars+1): {expected_vocab}")

# Check if output size matches
output_size = 735400
T = 40
actual_vocab = output_size // T
print(f"Actual vocab size (from output): {actual_vocab}")
print(f"Difference from expected: {actual_vocab - expected_vocab}")
