# UNLXCK Fight Camp Builder

This repository generates fight camp programs by combining local training modules. The main script reads athlete data, assembles strength, conditioning, recovery and other blocks, then exports the result directly to Google Docs.

Recent updates removed the OpenAI dependency and now build plans entirely from the module outputs. Short-camp handling and style-specific rules still adjust the phase weeks correctly via the helper `_apply_style_rules()`.
