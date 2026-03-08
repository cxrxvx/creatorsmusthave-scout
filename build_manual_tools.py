import json
import os

new_tools = [
    # AI Video Generation
    {"name": "HeyGen", "description": "AI video platform that creates studio-quality videos with realistic AI avatars and voices for content creators and marketers", "website": "heygen.com"},
    {"name": "Synthesia", "description": "AI video generation platform that creates professional videos with AI avatars from text scripts, used by creators and businesses", "website": "synthesia.io"},
    {"name": "InVideo AI", "description": "AI video creation platform that turns text prompts and scripts into fully edited videos for YouTube, social media and marketing", "website": "invideo.io"},
    {"name": "Fliki AI", "description": "AI tool that converts text and blog posts into videos with realistic AI voiceovers for content creators", "website": "fliki.ai"},
    {"name": "Pictory", "description": "AI video creation tool that automatically converts long-form content like blogs and scripts into short branded videos", "website": "pictory.ai"},
    {"name": "Colossyan", "description": "AI video platform for creating training and explainer videos using AI avatars without cameras or studios", "website": "colossyan.com"},
    {"name": "Runway ML", "description": "AI creative platform for video generation, editing and visual effects used by filmmakers and content creators", "website": "runwayml.com"},
    {"name": "Zebracat AI", "description": "AI video generator that creates faceless videos from text prompts for YouTube automation and social media creators", "website": "zebracat.ai"},
    {"name": "Veed AI", "description": "Online video editor with AI tools for subtitles, transcription, translation and video enhancement for content creators", "website": "veed.io"},

    # AI Voice / Audio
    {"name": "Murf AI", "description": "AI voice generator that creates studio-quality voiceovers in 120+ voices and 20 languages for videos, podcasts and presentations", "website": "murf.ai"},
    {"name": "Play.ht", "description": "AI text-to-speech platform with ultra-realistic voices for creating voiceovers, podcasts and audio content", "website": "play.ht"},
    {"name": "Lalal AI", "description": "AI audio tool that separates vocals from instrumentals and removes background noise from audio and video files", "website": "lalal.ai"},
    {"name": "Lovo AI", "description": "AI voice generator and text-to-speech platform with 500+ voices for content creators, podcasters and video producers", "website": "lovo.ai"},
    {"name": "Speechify", "description": "AI text-to-speech app that reads any content aloud at high speed, used by creators for content consumption and voiceovers", "website": "speechify.com"},
    {"name": "Resemble AI", "description": "AI voice cloning platform that creates custom AI voices and realistic speech synthesis for creators and developers", "website": "resemble.ai"},

    # AI Writing / Content
    {"name": "Copy.ai", "description": "AI copywriting platform that generates marketing copy, blog posts, social media content and sales emails for creators and marketers", "website": "copy.ai"},
    {"name": "Writesonic", "description": "AI writing assistant that creates SEO-optimised blog posts, ads, landing pages and social media content for marketers and creators", "website": "writesonic.com"},
    {"name": "Rytr", "description": "AI writing tool that generates blog posts, emails, social media captions and marketing copy in 40+ languages", "website": "rytr.me"},
    {"name": "Hypotenuse AI", "description": "AI content platform that generates product descriptions, blog articles and marketing copy at scale for ecommerce and content teams", "website": "hypotenuse.ai"},
    {"name": "Scalenut", "description": "AI SEO and content marketing platform that researches, plans and writes long-form SEO content for bloggers and marketers", "website": "scalenut.com"},
    {"name": "Frase", "description": "AI SEO content tool that researches top-ranking pages, generates content briefs and writes SEO-optimised articles", "website": "frase.io"},
    {"name": "Anyword", "description": "AI copywriting platform with predictive performance scoring that generates and optimises marketing copy for better conversions", "website": "anyword.com"},
    {"name": "Narrato AI", "description": "AI content creation and workflow platform for content teams to plan, write, optimise and publish content at scale", "website": "narrato.io"},
    {"name": "KoalaWriter", "description": "AI blog writing tool that generates long-form SEO articles with real-time data and automatic internal linking", "website": "koala.sh"},
    {"name": "BrandWell AI", "description": "AI content platform that creates long-form SEO blog posts and brand content from a single keyword", "website": "brandwell.ai"},

    # AI SEO Tools
    {"name": "NeuronWriter", "description": "AI SEO content editor that analyses competitor content and guides writers to create better-ranking articles", "website": "neuronwriter.com"},
    {"name": "Surfer SEO", "description": "AI SEO tool that analyses search results and provides real-time content optimisation guidelines for ranking blog posts", "website": "surferseo.com"},
    {"name": "RankIQ", "description": "AI SEO toolset for bloggers that identifies low-competition keywords and creates content briefs for faster ranking", "website": "rankiq.com"},
    {"name": "GrowthBar AI", "description": "AI SEO tool that generates SEO-optimised blog posts and provides keyword research for bloggers and content marketers", "website": "growthbarseo.com"},
    {"name": "Outranking", "description": "AI SEO writing platform that creates and optimises long-form content with automated internal linking and SERP analysis", "website": "outranking.io"},

    # AI Image / Design
    {"name": "Leonardo AI", "description": "AI image generation platform for creating game assets, concept art, marketing visuals and creative content at scale", "website": "leonardo.ai"},
    {"name": "AdCreative AI", "description": "AI advertising creative platform that generates high-converting ad creatives, banners and social media visuals for marketers", "website": "adcreative.ai"},
    {"name": "Predis AI", "description": "AI social media content generator that creates posts, carousels, videos and ad creatives from a single prompt", "website": "predis.ai"},
    {"name": "Looka", "description": "AI logo design and brand identity platform that generates professional logos and brand kits for creators and small businesses", "website": "looka.com"},
    {"name": "NightCafe", "description": "AI art generator that creates images from text prompts using multiple AI models for digital artists and content creators", "website": "nightcafe.studio"},
    {"name": "Ideogram AI", "description": "AI image generator specialised in creating images with accurate text rendering for posters, thumbnails and graphic design", "website": "ideogram.ai"},
    {"name": "Stockimg AI", "description": "AI design platform that generates stock photos, logos, book covers, posters and social media visuals on demand", "website": "stockimg.ai"},

    # AI Productivity / Work
    {"name": "Gamma AI", "description": "AI presentation and document creator that generates beautiful slide decks, documents and webpages from text prompts", "website": "gamma.app"},
    {"name": "Taskade AI", "description": "AI productivity platform that combines task management, mind mapping and AI agents for creators and remote teams", "website": "taskade.com"},
    {"name": "Motion AI", "description": "AI calendar and task manager that automatically schedules tasks and meetings based on priorities and deadlines", "website": "usemotion.com"},
    {"name": "SaneBox", "description": "AI email management tool that automatically filters, prioritises and organises email for professionals and creators", "website": "sanebox.com"},
    {"name": "Fireflies AI", "description": "AI meeting assistant that records, transcribes and summarises meetings with searchable notes and action items", "website": "fireflies.ai"},
    {"name": "MeetGeek AI", "description": "AI meeting recorder and summariser that automatically captures key moments and action items from video calls", "website": "meetgeek.ai"},

    # AI Chatbots / Agents
    {"name": "Chatbase", "description": "AI chatbot builder that trains custom ChatGPT-powered chatbots on your content for customer support and lead generation", "website": "chatbase.co"},
    {"name": "Tidio AI", "description": "AI customer service platform with live chat and chatbot that helps online businesses automate support and increase sales", "website": "tidio.com"},
    {"name": "ManyChat AI", "description": "AI chat marketing platform that automates Instagram, Facebook and WhatsApp conversations to grow creator audiences", "website": "manychat.com"},

    # AI Marketing / Social
    {"name": "Ocoya", "description": "AI social media content creation and scheduling platform that generates captions, hashtags and visuals for all platforms", "website": "ocoya.com"},
    {"name": "Instantly AI", "description": "AI cold email outreach platform that automates personalised email campaigns for creators and agencies", "website": "instantly.ai"},
    {"name": "Durable AI", "description": "AI website builder that creates a complete business website with copy and images in under 30 seconds", "website": "durable.co"},

    # AI Website / Builders
    {"name": "10Web AI", "description": "AI WordPress website builder that generates complete websites with content and images from a business description", "website": "10web.io"},
    {"name": "Webflow", "description": "Visual web design platform with AI tools that lets creators build professional websites without coding", "website": "webflow.com"},

    # AI Research / Docs
    {"name": "Originality AI", "description": "AI content detector and plagiarism checker that identifies AI-generated content for publishers and content teams", "website": "originality.ai"},
    {"name": "Grammarly", "description": "AI writing assistant that checks grammar, style, clarity and tone across all writing platforms for creators and professionals", "website": "grammarly.com"},
    {"name": "QuillBot", "description": "AI paraphrasing and writing tool that rewrites, summarises and improves text for students, writers and content creators", "website": "quillbot.com"},
]

# Load existing manual_tools.json
manual_file = os.path.expanduser("~/cxrxvx-ai-empire/memory/manual_tools.json")
existing = json.load(open(manual_file)) if os.path.exists(manual_file) else []

# Get existing names to avoid duplicates
existing_names = {t.get("name", "").lower() for t in existing}

added = 0
skipped = 0
for tool in new_tools:
    if tool["name"].lower() in existing_names:
        print(f"  ⏭️  Already exists: {tool['name']}")
        skipped += 1
    else:
        existing.append({
            "name": tool["name"],
            "description": tool["description"],
            "website": tool["website"],
            "status": "pending"
        })
        print(f"  ✅ Added: {tool['name']}")
        added += 1

json.dump(existing, open(manual_file, "w"), indent=2)
print(f"\nDone — {added} added, {skipped} skipped. Total: {len(existing)}")
