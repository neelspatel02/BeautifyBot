# BeautifyBot 📝

A Reddit bot that improves readability of text posts using AI.

- Listens for the trigger `!beautify` in subreddit comments
- Uses Groq LLM API to improve grammar, structure, and readability
- Replies directly with beautified text
- If the post was already beautified, then replies with the link to pervious responce.

Still in testing phase

## 🔮 Future Features
- Queuing system for handling multiple requests at once
- Support for replies and posts with media (links, photos, videos) + long body text
- Parameterized commands:
  - `!beautify -tldr` → generates only a TL;DR of the post
  - `!beautify -translate` → translates the text into a target language


*Personal bot mode: If the free tier window seems to run out too quickly then, will probably make this a personal bot (that will respond only to requests from personal account/s) to saves AI cost (fits free-tier limits for features like translation, artical summery from a link etc...)*
