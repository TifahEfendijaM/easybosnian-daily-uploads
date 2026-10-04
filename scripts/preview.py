"""Unpublished renderer fixtures. These are drawn backgrounds, not FLUX output."""
import copy
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from easybosnian.core import ROOT, write_json
from easybosnian.hybrid import render_hybrid as render, default_plan, editorial_plan


def package():
    base={"schema_version":1,"project":"tifahefendijam-easybosnian-daily-uploads-v1","date":"2026-10-02",
      "theme":{"name":"Kišni dan","equivalence_keys":["kišni dan","rainy weather","kišovito vrijeme","rain"]},
      "words":[{"lemma":"kišobran","equivalence_keys":["umbrella","kišobrani","kisobran"]},{"lemma":"oblak","equivalence_keys":["cloud","oblaci"]},{"lemma":"kap","equivalence_keys":["drop","kapljica","kapi"]}],
      "design_palette":"blue-ice","caption":"Tri kratka izazova za danas! U kvizu izaberi A, B ili C i napiši svoj izbor u komentaru. Zatim pročitaj zanimljivost i upotrijebi novu riječ u svojoj rečenici.",
      "hashtags":["#EasyBosnian","#BosanskiJezik","#UčiBosanski","#RiječDana"],
      "sources":[{"url":"https://www.pravopis.ba/pravopisni-rjecnik","title":"Pravopis bosanskoga jezika","supports":"Draft renderer fixture; individual dictionary entries still need verification before any history save.","checked_at":"2026-10-02T15:30:00+02:00"},{"url": "https://www.weather.gov/lmk/cloud_classification", "title": "National Weather Service: Cloud Classification", "supports": "Opened source corroborates that high-level clouds are primarily composed of ice crystals and often appear thin. Other fixture claims and live novelty remain unreviewed.", "checked_at": "2026-10-03T12:57:49.877814+00:00"}],
      "private_review":{"correct_option":"B","correct_text":"kišobran","explanation":"Ovaj predmet se otvara i drži iznad glave radi zaštite od kiše.","answer_aliases":["umbrella","suncobran"],"identifying_hints":["predmet koji se otvara iznad glave"],"standard_bosnian_checked":False,"sources_checked":False,"semantic_history_checked":False,"no_answer_leak_checked":False,"history_checked_at":"2026-10-02T15:30:00+02:00","reviewed_at":"2026-10-02T15:30:00+02:00","reviewer":"RENDERER FIXTURE — DO NOT SAVE AS REVIEWED","notes":"Unpublished design fixture. Not researched or checked against live Cloudflare history; flags intentionally false."},
      "cards":[
        {"kind":"quiz","word":"kišobran","question":"Šta nosimo da se zaštitimo od kiše?","options":[{"label":"A","text":"torbu"},{"label":"B","text":"kišobran"},{"label":"C","text":"knjigu"}],"alt_text":"Pitanje dana s tri mogućnosti. Izaberi A, B ili C.","background_prompt":"Photorealistic close-up photograph of rain droplets on plain glass, with softly blurred blue and grey scenery beyond. Gentle overcast daylight, realistic reflections and a calm atmosphere. No text, no lettering, no logos."},
        {"kind":"lesson","word":"oblak","heading":"Oblak","body":"Tanki oblaci visoko na nebu mogu biti sastavljeni od sitnih kristala leda. Iako izgledaju mekano, iznad nas tada lebdi led.","alt_text":"Znaš li? Zanimljivost o ledu u visokim oblacima.","background_prompt":"Photorealistic photograph of thin, wispy clouds high above a distant mountain ridge. Gentle daylight, cool blue and grey tones, realistic atmospheric detail. Keep the mountains low in the frame with a broad, simple sky above. No text, no lettering, no logos."},
        {"kind":"word","word":"kap","heading":"Kap","body":"Vrlo mala količina tečnosti, obično zaobljenog oblika.","example":"Kap vode je pala na sto.","alt_text":"Riječ dana: kap, uz kratko značenje i primjer upotrebe.","background_prompt":"Photorealistic macro photograph of a single clear water droplet resting on a real leaf. Natural morning light, realistic reflections, true-to-life green and blue colours, shallow depth of field and natural botanical textures. No text, no lettering, no logos."}
      ]}
    # Option inflection must match the private answer and word metadata consistently.
    base["cards"][0]["options"][0]["text"]="torba"
    base["cards"][0]["options"][2]["text"]="knjiga"
    base["cards"][0]["question"]="Koji predmet koristimo da se zaštitimo od kiše?"
    return base


def scene(path, kind, palette='blue-ice'):
    p=json.loads((ROOT / 'data/design-palettes.json').read_text())[palette]
    def rgb(h): return tuple(int(h[i:i+2],16) for i in (1,3,5))
    top,bottom=rgb(p['scrim']),rgb(p['accent'])
    image=Image.new('RGB',(1080,1350)); d=ImageDraw.Draw(image)
    for y in range(1350):
        t=(y/1350)**1.2
        d.line((0,y,1080,y),fill=tuple(round(a*(1-t)+b*t*.78) for a,b in zip(top,bottom)))
    art=Image.new('RGBA',image.size); a=ImageDraw.Draw(art)
    rnd=random.Random(kind)
    if kind=='quiz':
        for _ in range(90):
            x,y=rnd.randrange(0,1080),rnd.randrange(450,1350); r=rnd.randrange(4,15)
            a.ellipse((x-r,y-r,x+r,y+r*1.6),fill=(*rgb(p['panel']),rnd.randrange(15,80)))
            a.arc((x-r,y-r,x+r,y+r*1.6),40,160,fill=(*rgb(p['panel']),140),width=2)
        a.line((720,860,570,1350),fill=(*rgb(p['panel']),90),width=3)
    elif kind=='lesson':
        for cx,cy,scale in [(780,990,1.3),(500,1110,1.0),(180,1060,.6)]:
            for dx,dy,r in [(-140,0,100),(0,-50,140),(150,10,110)]:
                x,y=round(cx+dx*scale),round(cy+dy*scale); radius=round(r*scale)
                a.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(*rgb(p['panel']),100))
        a.polygon([(0,1230),(220,1120),(400,1200),(690,1100),(1080,1220),(1080,1350),(0,1350)],fill=(*top,190))
        art=art.filter(ImageFilter.GaussianBlur(18))
    else:
        a.ellipse((280,900,1010,1190),fill=(*rgb(p['ink']),240))
        a.line((310,1065,1040,1090),fill=(*rgb(p['accent']),160),width=4)
        for x,y,r in [(650,1000,55),(840,1040,29),(430,1060,19)]:
            a.ellipse((x-r,y-r,x+r,y+r),fill=(*rgb(p['accent']),165),outline=(*rgb(p['panel']),200),width=3)
            a.ellipse((x-r//2,y-r//2,x-r//5,y-r//5),fill=(*rgb(p['panel']),210))
    Image.alpha_composite(image.convert('RGBA'),art).convert('RGB').save(path,'JPEG',quality=95)


def main():
    output=ROOT / 'build/previews'; output.mkdir(parents=True,exist_ok=True)
    p=package(); write_json(ROOT / 'examples/renderer-draft.json',p)
    metrics=[]
    for c in p['cards']:
        bg=output / (c['kind']+'-background.jpg'); scene(bg,c['kind'])
        metrics.append(render(c,p['design_palette'],bg,output / (c['kind']+'.jpg')))
    sheet=Image.new('RGB',(1080,450))
    for i,c in enumerate(p['cards']):
        sheet.paste(Image.open(output / (c['kind']+'.jpg')).resize((360,450)),(i*360,0))
    sheet.save(output / 'carousel-preview.jpg',quality=95)
    gallery=Image.new('RGB',(1080,450))
    for i,style in enumerate(('rounded','outlined','editorial')):
        card=copy.deepcopy(p['cards'][2]);plan=editorial_plan(card) if style=='editorial' else default_plan(card)
        if style=='outlined':plan['blocks'][0]['style']='outlined'
        path=output / (style+'.jpg');render(card,p['design_palette'],output/'word-background.jpg',path,plan)
        gallery.paste(Image.open(path).resize((360,450)),(i*360,0))
    gallery.save(output / 'supported-designs.jpg',quality=95)
    write_json(output / 'metrics.json',metrics)
    print('Unpublished draft previews created; drawn fixture backgrounds, not FLUX')


if __name__=='__main__': main()
