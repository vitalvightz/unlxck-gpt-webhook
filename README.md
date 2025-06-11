# UNLXCK Fight Camp Builder

This repository generates fight camp programs by combining local training modules. The main script reads athlete data, assembles strength, conditioning, recovery and other blocks, then exports the result directly to Google Docs.

Recent updates removed the OpenAI dependency and now build plans entirely from the module outputs. Short-camp handling and style-specific rules still adjust the phase weeks correctly via the helper `_apply_style_rules()`.

### Professional Status

Setting the **Professional Status** field to `professional` shifts 5% of the camp length from GPP to SPP when the camp is at least four weeks long. GPP will never drop below 15% of total weeks.
