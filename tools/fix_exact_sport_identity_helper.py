from pathlib import Path

path = Path('tools/apply_exact_sport_identity_fix.py')
text = path.read_text(encoding='utf-8')
text = text.replace('        \\"wrestler\\": \\"wrestler\\",\\n        \\"wrestling\\": \\"wrestler\\",', '        \\"wrestler\\": \\"wrestling\\",\\n        \\"wrestling\\": \\"wrestling\\",')
text = text.replace('assert conditioning._style_specificity_sport_tag(\\"wrestling\\", \\"mma\\") == \\"wrestler\\"', 'assert conditioning._style_specificity_sport_tag(\\"wrestling\\", \\"mma\\") == \\"wrestling\\"')
path.write_text(text, encoding='utf-8')
