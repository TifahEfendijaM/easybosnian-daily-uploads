Evo kako se pokreće rerun i mijenja težina vokabulara (A1–C2), uz nove opcije:

Svako jutro u 5 se automatski pripreme tekstovi i slike, pa idu objave na IG, FB i TikTok, uz storije na IG i FB. Sve se izvršava u cloudu, tako da nijedan uređaj ne mora biti upaljen.

Rerun je tu ako rezultat nije dobar ili želite sami odabrati sadržaj.

Otvorite ovu stranicu:
https://github.com/TifahEfendijaM/easybosnian-daily-uploads/actions/workflows/preparation.yml
→ Run workflow. Ostavite main, izaberite daily i jednu opciju:

- same_words: iste riječi i tema, novi tekstovi, slike i dizajn.
- same_theme: ista tema, nove riječi i sadržaj.
- new: nova tema i riječi.
- custom: Vi zadajete temu i riječi.

U zadnjem meniju, batch_target, birate šta se zamjenjuje:

- latest: posljednji sačuvani paket, radi i poslije ponoći.
- none: dodaje još jednu objavu, bez brisanja prethodnih.
- all_today: zamjenjuje sve ranije današnje pakete i briše njihove teme i riječi iz historije. Ako danas nema ništa, samo dodaje novu objavu, ne dira jučerašnje.

Ostala polja koristite samo za custom. Prvo je tema; prazno zadržava postojeću. Za svaku karticu keep_today zadržava riječ, chatgpt bira novu, a uz entered upišite svoju. Za Znaš li možete upisati i poređenje ili kratku temu. Zatim kliknite zeleno Run workflow.

Kod zamjene se pokušaju obrisati odgovarajuće IG objave i storiji te FB objave. Ako brisanje ne uspije, nove objave ipak idu. Stari TikTok sadržaj i FB storiji brišu se ručno.

Kad run završi, otvorite ga i pogledajte Summary. Kod uspješnog runa tu je izvještaj s temom, nivoom, promptovima za slike i linkovima do objava. Kopije izvještaja možete preuzeti pod Artifacts.

Nivo sada birate u istom Run workflow meniju, u polju difficulty. Za new/same_theme odaberite A1–C2 ili random. Random češće bira početne nivoe, a tako radi i jutarnja automatika. Novoizabrane custom riječi prate taj izbor, dok zadržane riječi čuvaju svoj nivo. Stari zasebni workflow za nivo je trenutno neaktivan.

Za A1/A2 su objašnjenja i definicije na engleskom, dok riječi, odgovori i primjeri ostaju na bosanskom. Od B1 nadalje i objašnjenja su na bosanskom.
