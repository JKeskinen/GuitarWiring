#!/usr/bin/env python3
"""
Refactoring script to complete the modularization of main.py.
This script extracts all step logic and creates proper step modules.
"""

import os
import re

# Base paths
app_dir = r"C:\Users\juhok\Documents\Opinnot\SYKSY2025\Tekoälykurssi\TekoAlyLopputyo\app"
steps_dir = os.path.join(app_dir, "steps")
main_file = os.path.join(app_dir, "main.py")

# Read the original main.py
with open(main_file, 'r', encoding='utf-8') as f:
    main_content = f.read()

# Find all 'with st.expander' blocks for steps 4-7
step_patterns = {
    4: r"with st\.expander\('Step 4 — Measurements'.*?\n(?=with st\.expander\('Step 5|if __name__|# Persist)",
    5: r"with st\.expander\('Step 5 — Phase checks'.*?\n(?=with st\.expander\('Step 6|if __name__|# Persist)",
    6: r"with st\.expander\('Step 6 — Analysis'.*?\n(?=with st\.expander\('Step 7|if __name__|# Persist)",
    7: r"with st\.expander\('Step 7 — Switch Setup'.*?\n(?=if __name__|# Persist)",
}

for step_num, pattern in step_patterns.items():
    match = re.search(pattern, main_content, re.DOTALL)
    if match:
        print(f"Step {step_num}: Found {len(match.group())} characters")
    else:
        print(f"Step {step_num}: Not found")

print("\nTotal main.py lines:", len(main_content.split('\n')))
