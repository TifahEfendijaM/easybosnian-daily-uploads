Evo ukratko kako ovo radi: svako jutro u 5, po našem vremenu, Cloudflare pokrene proces na GitHubu. ChatGPT izabere temu i sadržaj, provjeri ranije korištene riječi, napiše tekstove i opise, FLUX napravi pozadine, a Pillow doda tekst i logo. Onda idu objave na Instagram, Facebook i TikTok, plus storiji na IG i FB. Sve radi u cloudu, ne treba otvoren laptop.

Rerun je tu ako nam jutarnja objava nije ispala kako treba i/ili želimo sami odabrati sadržaj.

Za rerun otvori https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml → Run workflow. Ostavi main, za mode izaberi daily, pa content_selection:
- same_words: ista tema i riječi, ali novi tekstovi, opisi, slike i izbor dizajna.
- same_theme: ista tema, nove riječi i sav novi sadržaj.
- new: nova tema, riječi i sadržaj.
- custom: sami zadajemo temu i riječi/temu za Znaš li.

Polja ispod koristiš samo za custom, za ostale opcije ih slobodno ignoriši. Prvo prazno polje je tema; prazno znači zadrži temu iz posljednjeg sačuvanog paketa za taj dan. Za svaku karticu: keep_today = zadrži njenu riječ/temu i ostavi polje prazno; chatgpt = neka izabere i ostavi prazno; entered = upiši šta želiš. Za Znaš li možeš upisati i poređenje, npr. peći / kuhati, ili kratku temu. Tekstovi se ponovo pišu i kad zadržimo iste riječi.

Na kraju klikni zeleno Run workflow. Možeš zatvoriti tab kad se novi run pojavi. Ako danas još nema sačuvanog sadržaja, kreni s new ili popuni custom.

Rerun pokušava obrisati samo posljednju objavu i njene storije za taj dan na IG, a na FB posljednju feed objavu. Ako brisanje ne uspije, nova objava ipak ide. Stare TikTok objave i FB storije brišemo ručno ako želimo.

Nivo mijenjaš odvojeno: https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/configure-level.yml → Run workflow → main → izaberi A1–C2 → zeleno Run workflow. Kad uspješno završi, nivo je sačuvan za buduće automatske i ručne pripreme dok ga opet ne promijenimo. Ovo samo mijenja postavku, ne objavljuje ništa. Nivo vodi izbor novih riječi i sadržaja; zadržane ili ručno unesene riječi zadržavaju svoj procijenjeni nivo.

Repo je privatan, pa ti prvo treba pristup preko GitHub naloga.
