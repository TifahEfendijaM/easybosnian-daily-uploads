Svako jutro u 5 se automatski pripreme tekstovi i slike, pa idu objave na IG, FB i TikTok, uz storije na IG i FB. Laptop ne mora biti upaljen. Rerun je tu ako rezultat nije dobar ili želite sami odabrati sadržaj. Zamjenjuje posljednji sačuvani paket, čak i poslije ponoći.

Za rerun otvorite [ovu stranicu](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml) → Run workflow. Ostavite main, izaberite daily i jednu opciju:

- same_words: iste riječi, novi tekstovi, slike i dizajn.
- same_theme: ista tema, nove riječi.
- new: nova tema i riječi.
- custom: Vi zadajete temu i riječi.

Ostavite batch_target na latest. Ostala polja koristite samo za custom: prvo je tema, prazno zadržava postojeću. Za svaku karticu keep_today zadržava riječ/temu, chatgpt bira novu, a uz entered upišite svoju. Za Znaš li možete upisati i poređenje ili kratku temu. Zatim kliknite zeleno Run workflow.

Rerun pokušava obrisati posljednju IG objavu i njene storije te FB objavu. Ako brisanje ne uspije, nova objava ipak ide. Stari TikTok i FB storiji brišu se ručno.

Nivo mijenjate [ovdje](https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/configure-level.yml): Run workflow → main → A1–C2 → zeleno Run workflow. Kad završi, nivo ostaje za buduće pripreme dok ga opet ne promijenite; ovo samo mijenja postavku, ništa ne objavljuje.
