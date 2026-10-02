# Free services and cost boundary

Verified against official documentation on 2026-10-02. This project uses no paid OpenAI API, R2 checkout, posting service, paid fallback or automatic plan upgrade. It stops at free limits.

| Service | Documented free allowance | Project use |
|---|---|---|
| Workers AI | 10,000 neurons/day, reset 00:00 UTC | Three FLUX.1 Schnell images/day, four steps each. Documented rate: 4.8 neurons per 512×512 tile plus 9.6 per step. At 1024², about 57.6 neurons/image, 172.8/day. Exact output size/usage is provider-controlled. |
| Workers | 100,000 requests/day, 10ms CPU/invocation | Small private API, cached public JPEGs and one daily health check; generation runs on AI infrastructure. Monitor CPU limit errors. |
| KV | 1GB, 100,000 reads/day, 1,000 writes/list/deletes per day | 14-day TTL; six private JPEGs plus three public copies/day, max 3MB each, plus three cached base64 AI responses. Roughly 400–550MB at maximum image bounds. Repeated exposures also consume space/operations. |
| D1 | 5 million rows read/day, 100,000 rows written/day, 5GB total | Permanent history/reservations and small batch state. No automatic deletion. |
| GitHub Free | 2,000 standard runner minutes/month, 500MB shared artifact/Packages storage | Linux runners only; 15-minute job ceiling; seven-day diagnostics. Account allowances are shared with other work, without inspecting or modifying other repositories. |
| Healthchecks Hobbyist | 20 monitored jobs, 100 log entries/job | Three checks for preparation, pipeline and monitoring. Email alerts; no paid phone/SMS integration. |

Use the **Workers Free plan**. The deployment helper rejects an identified paid Workers subscription. In GitHub Billing, set an Actions budget of **$0** with usage blocked at its limit, especially if the account already has a payment method. Do not raise the budget or enable paid Workers to solve a quota failure. A quota failure is reported and waits for a deliberate action or the next day's independently new batch.

Official sources:

- [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [FLUX.1 Schnell schema](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/)
- [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)
- [KV pricing](https://developers.cloudflare.com/kv/platform/pricing/)
- [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Healthchecks pricing](https://healthchecks.io/pricing/)
- [GitHub timezone-aware schedule syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onschedule)
