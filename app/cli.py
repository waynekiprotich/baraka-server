"""Flask CLI commands: create-admin, seed, seed-demo."""

from __future__ import annotations

from datetime import timedelta

import click
from flask import current_app
from flask.cli import with_appcontext
from PIL import Image, ImageDraw
from sqlalchemy import select

from .errors import ApiError
from .extensions import db
from .models import Event, GalleryCategory, GalleryImage, NewsArticle, utcnow
from .services import auth_service, settings_service, supabase_storage
from .slugs import slugify

# Created by `flask seed`. Order matters: it becomes the tab order on /gallery.
GALLERY_CATEGORIES = [
    ("Academics", "Classrooms, laboratories and learning across every grade."),
    ("Sports", "Athletics, football, volleyball, netball and swimming."),
    ("Events", "Music festival, prize giving, open days and school trips."),
    ("Campus", "The grounds, the science and ICT block, and the school garden."),
]

# --- demo content ---------------------------------------------------------
# Every line below is drawn from SPEC section 2. Nothing here is a new claim
# about the school; it is existing site copy rearranged into sample rows so a
# developer can see the templates full. `flask seed-demo` refuses to run
# outside development.

DEMO_NOTE = "Sample content loaded by `flask seed-demo` for local development."

DEMO_NEWS = [
    {
        "title": "Full CBC transition completed across every grade",
        "category": "Academics",
        "author": "Baraka School Kapsabet",
        "excerpt": (
            "Every grade is now fully aligned to the Competency-Based Curriculum, "
            "from Playgroup through Grade 9."
        ),
        "body": (
            "Since 2023 every grade at Baraka School Kapsabet has been fully aligned to the "
            "Competency-Based Curriculum.\n\n"
            "Competency is tracked individually rather than against a class average, and "
            "parents are briefed each term with a written progress narrative. Lessons move at "
            "the pace of understanding: learners are taught to mastery, not to the calendar."
        ),
        "days_ago": 6,
    },
    {
        "title": "Junior School pathways: STEM, Social Sciences, Arts & Sports Science",
        "category": "Academics",
        "author": "Mr. Samuel Kiptoo",
        "excerpt": (
            "Grades 7 to 9 explore three pathways alongside career guidance and "
            "senior-school placement preparation."
        ),
        "body": (
            "Junior School at Baraka covers Grades 7 to 9, with pathway exploration across "
            "STEM, Social Sciences, and Arts & Sports Science.\n\n"
            "Alongside the pathways, learners take part in leadership programmes and receive "
            "career guidance and senior-school placement preparation. Ninety-eight per cent of "
            "our learners transition to their first-choice senior school."
        ),
        "days_ago": 20,
    },
    {
        "title": "Six clubs, one afternoon: inside school life at Baraka",
        "category": "School life",
        "author": "Baraka School Kapsabet",
        "excerpt": (
            "Little Explorers, Clay Modeling, Puppet Theatre, STEM & Coding, Scouts and the "
            "Debate Society."
        ),
        "body": (
            "Club afternoons run across the school. The named clubs are Little Explorers, "
            "Clay Modeling, Puppet Theatre, STEM & Coding, Scouts and the Debate Society.\n\n"
            "“Debate club taught me to disagree without being disagreeable,” says Faith, "
            "Grade 8. Brian, Grade 6, built his first working robot in the STEM club this year."
        ),
        "days_ago": 34,
    },
    {
        "title": "Science and ICT block: practical learning capacity doubled",
        "category": "Campus",
        "author": "Baraka School Kapsabet",
        "excerpt": (
            "The purpose-built laboratories opened in 2019 and doubled the school's "
            "practical-learning capacity."
        ),
        "body": (
            "The new science and ICT block opened in 2019 with purpose-built laboratories that "
            "doubled practical-learning capacity.\n\n"
            "Hands-on laboratory work begins in Grade 4. Every classroom is equipped for "
            "supervised digital learning, from Grade 4 coding clubs through to Junior School "
            "research skills, paired with clear screen-time guidelines."
        ),
        "days_ago": 52,
    },
]

DEMO_EVENTS = [
    {
        "title": "Term 1 begins",
        "summary": "Term 1 runs from 6 January to 4 April.",
        "description": (
            "Term 1 opens for Playgroup through Grade 9. Term 1 runs from 6 January to "
            "4 April."
        ),
        "location": "Baraka School Kapsabet, Kapsabet–Eldoret Road",
        "days_ahead": 12,
        "duration_hours": 8,
    },
    {
        "title": "Admissions open day — 2027 intake",
        "summary": "Meet the teaching team and walk the grounds.",
        "description": (
            "Places are open for Playgroup through Grade 9 for the 2027 intake. Come and meet "
            "the teaching team, see the classrooms and the science and ICT block, and talk "
            "through the admissions process: submit an enquiry, then a short friendly "
            "placement assessment for learner and parents, then offer and enrolment."
        ),
        "location": "Baraka School Kapsabet, Kapsabet–Eldoret Road",
        "days_ahead": 26,
        "duration_hours": 5,
    },
    {
        "title": "Annual Music Festival",
        "summary": "The Music & Choir programme's annual festival.",
        "description": (
            "The annual Music Festival brings together the Music & Choir programme across "
            "every grade, alongside work from the Drama and Art Studio programmes."
        ),
        "location": "School hall",
        "days_ahead": 48,
        "duration_hours": 4,
    },
    {
        "title": "Inter-house football league final",
        "summary": "The closing fixture of the inter-house league.",
        "description": (
            "The inter-house football league closes with the final fixture of the season. "
            "Football at Baraka runs as inter-house leagues alongside county tournaments."
        ),
        "location": "School playing field",
        "days_ahead": 61,
        "duration_hours": 3,
    },
]

# Flat placeholder artwork generated locally so the gallery has real files to
# serve. Swap these for school photographs from the dashboard.
DEMO_IMAGES = [
    ("Academics", "A Grade 5 science lesson in the school laboratory", (42, 17, 85)),
    ("Academics", "Learners working through a numeracy task in class", (60, 30, 114)),
    ("Sports", "Athletics training on the school field at Kapsabet", (78, 42, 142)),
    ("Sports", "An inter-house football fixture in progress", (184, 134, 43)),
    ("Events", "The school choir performing at the annual Music Festival", (31, 122, 77)),
    ("Events", "Parents and learners at an admissions open day", (154, 107, 18)),
    ("Campus", "The science and ICT block seen from the courtyard", (85, 76, 69)),
    ("Campus", "The school garden used for practical agriculture lessons", (25, 21, 18)),
]


def register_cli(app) -> None:
    app.cli.add_command(create_admin_command)
    app.cli.add_command(seed_command)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(setup_storage_command)


@click.command("create-admin")
@click.option("--email", prompt="Email", help="Sign-in address for the new administrator.")
@click.option("--name", prompt="Full name", help="Display name for the new administrator.")
@click.password_option(
    "--password",
    prompt="Password",
    confirmation_prompt="Confirm password",
    help="At least 10 characters.",
)
@with_appcontext
def create_admin_command(email: str, name: str, password: str) -> None:
    """Create an administrator account."""
    try:
        user = auth_service.create_admin(email=email, name=name, password=password)
    except ApiError as exc:
        detail = "; ".join(f"{key}: {value}" for key, value in (exc.fields or {}).items())
        raise click.ClickException(detail or exc.message) from exc
    click.echo(f"Created administrator {user.email} (id {user.id}).")


@click.command("setup-storage")
@with_appcontext
def setup_storage_command() -> None:
    """Create the configured Supabase Storage bucket as public. Idempotent."""
    if not supabase_storage.is_configured():
        raise click.ClickException(
            "SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and SUPABASE_STORAGE_BUCKET must all be "
            "set (in .env) before the bucket can be created."
        )
    try:
        supabase_storage.ensure_public_bucket()
    except supabase_storage.SupabaseStorageError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Bucket '{current_app.config['SUPABASE_STORAGE_BUCKET']}' is ready (public).")


@click.command("seed")
@with_appcontext
def seed_command() -> None:
    """Create the site settings and gallery categories. Idempotent."""
    created_settings = settings_service.ensure_defaults()

    created_categories = 0
    for position, (name, description) in enumerate(GALLERY_CATEGORIES, start=1):
        slug = slugify(name)
        existing = db.session.execute(
            select(GalleryCategory).where(GalleryCategory.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.session.add(
            GalleryCategory(
                slug=slug, name=name, description=description, position=position
            )
        )
        created_categories += 1
    if created_categories:
        db.session.commit()

    click.echo(
        f"Seed complete: {created_settings} setting(s) and "
        f"{created_categories} gallery category/categories created."
    )


@click.command("seed-demo")
@click.option("--reset", is_flag=True, help="Delete existing demo rows first.")
@with_appcontext
def seed_demo_command(reset: bool) -> None:
    """Load sample news, events and gallery rows. Development only."""
    if current_app.config["ENV_NAME"] != "development":
        raise click.ClickException(
            "seed-demo only runs in development. Set FLASK_ENV=development to use it."
        )

    seed_command.callback()

    if reset:
        for slug in (slugify(item["title"]) for item in DEMO_NEWS):
            row = db.session.execute(
                select(NewsArticle).where(NewsArticle.slug == slug)
            ).scalar_one_or_none()
            if row is not None:
                db.session.delete(row)
        for slug in (slugify(item["title"]) for item in DEMO_EVENTS):
            row = db.session.execute(
                select(Event).where(Event.slug == slug)
            ).scalar_one_or_none()
            if row is not None:
                db.session.delete(row)
        for image in db.session.execute(
            select(GalleryImage).where(GalleryImage.storage_key.like("demo-%"))
        ).scalars().all():
            db.session.delete(image)
        db.session.commit()

    now = utcnow()
    news_created = 0
    for item in DEMO_NEWS:
        slug = slugify(item["title"])
        if db.session.execute(
            select(NewsArticle.id).where(NewsArticle.slug == slug)
        ).first():
            continue
        db.session.add(
            NewsArticle(
                slug=slug,
                title=item["title"],
                excerpt=item["excerpt"],
                body=f"{item['body']}\n\n{DEMO_NOTE}",
                category=item["category"],
                author=item["author"],
                is_published=True,
                published_at=now - timedelta(days=item["days_ago"]),
            )
        )
        news_created += 1

    events_created = 0
    for item in DEMO_EVENTS:
        slug = slugify(item["title"])
        if db.session.execute(select(Event.id).where(Event.slug == slug)).first():
            continue
        starts_at = (now + timedelta(days=item["days_ahead"])).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
        db.session.add(
            Event(
                slug=slug,
                title=item["title"],
                summary=item["summary"],
                description=f"{item['description']}\n\n{DEMO_NOTE}",
                starts_at=starts_at,
                ends_at=starts_at + timedelta(hours=item["duration_hours"]),
                location=item["location"],
                is_published=True,
            )
        )
        events_created += 1

    db.session.commit()

    images_created = _seed_demo_images()

    click.echo(
        f"Demo seed complete: {news_created} article(s), {events_created} event(s), "
        f"{images_created} gallery image(s)."
    )


def _seed_demo_images() -> int:
    """Write flat placeholder artwork to the uploads directory and record it."""
    upload_dir = current_app.config["UPLOAD_DIR"]
    upload_dir.mkdir(parents=True, exist_ok=True)

    categories = {
        category.name: category
        for category in db.session.execute(select(GalleryCategory)).scalars().all()
    }

    created = 0
    for index, (category_name, alt_text, colour) in enumerate(DEMO_IMAGES, start=1):
        storage_key = f"demo-{index:02d}.png"
        if db.session.execute(
            select(GalleryImage.id).where(GalleryImage.storage_key == storage_key)
        ).first():
            continue

        _write_placeholder(upload_dir / storage_key, 1600, 1067, colour)
        _write_placeholder(upload_dir / f"demo-{index:02d}_thumb.png", 480, 320, colour)

        db.session.add(
            GalleryImage(
                category_id=categories[category_name].id if category_name in categories else None,
                title=alt_text,
                alt_text=alt_text,
                url=f"/uploads/{storage_key}",
                thumb_url=f"/uploads/demo-{index:02d}_thumb.png",
                storage_key=storage_key,
                width=1600,
                height=1067,
                position=index,
                is_featured=index <= 6,
            )
        )
        created += 1

    if created:
        db.session.commit()
    return created


def _write_placeholder(path, width: int, height: int, colour: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (width, height), colour)
    draw = ImageDraw.Draw(image)
    lighter = tuple(min(255, channel + 26) for channel in colour)
    draw.rectangle(
        [(0, int(height * 0.62)), (width, height)],
        fill=lighter,
    )
    image.save(path, format="PNG", optimize=True)
    image.close()
