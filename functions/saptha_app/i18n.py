# i18n.py — Internationalization support for SapthaEvent
# Python 3.9 compatible

import os
from typing import Optional, Dict, Any
from flask import request, session, g


# ---------------------------------------------------------------------------
# Supported languages
# ---------------------------------------------------------------------------
SUPPORTED_LOCALES: Dict[str, Dict[str, str]] = {
    'en': {'name': 'English',  'native': 'English',  'dir': 'ltr', 'flag': '🇬🇧'},
}

DEFAULT_LOCALE = 'en'


# ---------------------------------------------------------------------------
# Locale resolution  (session → cookie → Accept-Language → default)
# ---------------------------------------------------------------------------
def get_locale() -> str:
    """Return the best locale for the current request."""
    # 1. Explicit session choice
    locale = session.get('locale')
    if locale and locale in SUPPORTED_LOCALES:
        return locale

    # 2. Persistent cookie
    locale = request.cookies.get('locale')
    if locale and locale in SUPPORTED_LOCALES:
        return locale

    # 3. Browser Accept-Language header
    best = request.accept_languages.best_match(SUPPORTED_LOCALES.keys())
    return best or DEFAULT_LOCALE


def get_translations(locale: Optional[str] = None) -> Dict[str, str]:
    """Return the translation dict for *locale* (defaults to current request locale)."""
    if locale is None:
        locale = get_locale()
    return TRANSLATIONS.get(locale, TRANSLATIONS[DEFAULT_LOCALE])


def t(key: str, locale: Optional[str] = None) -> str:
    """Shorthand: translate a single key."""
    translations = get_translations(locale)
    return translations.get(key, TRANSLATIONS[DEFAULT_LOCALE].get(key, key))


# ---------------------------------------------------------------------------
# Jinja2 helpers  — call  init_i18n(app)  once at startup
# ---------------------------------------------------------------------------
def init_i18n(app: Any) -> None:
    """Register i18n helpers on a Flask app."""

    @app.before_request
    def _set_locale() -> None:
        g.locale = get_locale()
        g.locale_dir = SUPPORTED_LOCALES[g.locale]['dir']
        g.translations = get_translations(g.locale)

    @app.context_processor
    def _inject_i18n() -> Dict[str, Any]:
        return {
            'current_locale': getattr(g, 'locale', DEFAULT_LOCALE),
            'locale_dir': getattr(g, 'locale_dir', 'ltr'),
            'supported_locales': SUPPORTED_LOCALES,
            '_t': lambda key: t(key, getattr(g, 'locale', DEFAULT_LOCALE)),
            'translations': getattr(g, 'translations', TRANSLATIONS[DEFAULT_LOCALE]),
        }


# ---------------------------------------------------------------------------
# Translation dictionaries
# ---------------------------------------------------------------------------
TRANSLATIONS: Dict[str, Dict[str, str]] = {

    # ── English ───────────────────────────────────────────────────────────
    'en': {
        # Navbar
        'nav_home':           'Home',
        'nav_events':         'Events',
        'nav_login':          'Login',
        'nav_logout':         'Logout',
        'nav_dashboard':      'Dashboard',
        'nav_tickets':        'My Tickets',

        # Hero
        'hero_title':         'Saptha — The Grand College Fest',
        'hero_subtitle':      'Experience an extraordinary celebration of talent, culture, and innovation.',
        'hero_cta_explore':   'Explore Events',
        'hero_cta_login':     'Login / Register',

        # Events
        'events_title':       'Featured Events',
        'events_subtitle':    'Discover a world of competitions, performances, and workshops.',
        'events_filter_all':       'All',
        'events_filter_technical': 'Technical',
        'events_filter_cultural':  'Cultural',
        'events_filter_sports':    'Sports',

        # Registration
        'register_btn':       'Register Now',
        'fee_free':           'Free',
        'fee_paid':           'Paid',

        # How It Works
        'how_title':          'How It Works',
        'how_subtitle':       'Getting started is easy — follow these simple steps.',
        'how_step1':          'Create your account or log in.',
        'how_step2':          'Browse and choose your favourite events.',
        'how_step3':          'Register and pay (if applicable).',
        'how_step4':          'Show your e-ticket at the venue — enjoy!',

        # Footer
        'footer_about':       'About Saptha',
        'footer_links':       'Quick Links',
        'footer_contact':     'Contact Us',
        'footer_copyright':   '© 2026 SapthaEvent — SNPSU. All rights reserved.',

        # Login
        'login_title':        'Welcome Back',
        'login_email':        'Email Address',
        'login_password':     'Password',
        'login_submit':       'Sign In',
        'login_forgot':       'Forgot password?',

        # Common UI
        'common_loading':     'Loading…',
        'common_error':       'Something went wrong.',
        'common_success':     'Success!',
        'common_cancel':      'Cancel',
        'common_save':        'Save',
        'common_delete':      'Delete',
        'common_search':      'Search…',

        # Dashboard
        'dashboard_title':         'Dashboard',
        'dashboard_events':        'My Events',
        'dashboard_registrations': 'Registrations',
        'dashboard_analytics':     'Analytics',
    },

    # ── Hindi ─────────────────────────────────────────────────────────────
    'hi': {
        # Navbar
        'nav_home':           'होम',
        'nav_events':         'कार्यक्रम',
        'nav_login':          'लॉगिन',
        'nav_logout':         'लॉगआउट',
        'nav_dashboard':      'डैशबोर्ड',
        'nav_tickets':        'मेरे टिकट',

        # Hero
        'hero_title':         'सप्त — भव्य कॉलेज उत्सव',
        'hero_subtitle':      'प्रतिभा, संस्कृति और नवाचार के असाधारण उत्सव का अनुभव करें।',
        'hero_cta_explore':   'कार्यक्रम देखें',
        'hero_cta_login':     'लॉगिन / रजिस्टर',

        # Events
        'events_title':       'प्रमुख कार्यक्रम',
        'events_subtitle':    'प्रतियोगिताओं, प्रदर्शनों और कार्यशालाओं की दुनिया खोजें।',
        'events_filter_all':       'सभी',
        'events_filter_technical': 'तकनीकी',
        'events_filter_cultural':  'सांस्कृतिक',
        'events_filter_sports':    'खेलकूद',

        # Registration
        'register_btn':       'अभी पंजीकरण करें',
        'fee_free':           'निःशुल्क',
        'fee_paid':           'सशुल्क',

        # How It Works
        'how_title':          'यह कैसे काम करता है',
        'how_subtitle':       'शुरू करना आसान है — इन सरल चरणों का पालन करें।',
        'how_step1':          'अपना खाता बनाएं या लॉगिन करें।',
        'how_step2':          'अपने पसंदीदा कार्यक्रम ब्राउज़ करें और चुनें।',
        'how_step3':          'पंजीकरण करें और भुगतान करें (यदि लागू हो)।',
        'how_step4':          'स्थल पर अपना ई-टिकट दिखाएं — आनंद लें!',

        # Footer
        'footer_about':       'सप्त के बारे में',
        'footer_links':       'त्वरित लिंक',
        'footer_contact':     'संपर्क करें',
        'footer_copyright':   '© 2026 सप्तइवेंट — SNPSU. सभी अधिकार सुरक्षित।',

        # Login
        'login_title':        'वापसी पर स्वागत',
        'login_email':        'ईमेल पता',
        'login_password':     'पासवर्ड',
        'login_submit':       'साइन इन',
        'login_forgot':       'पासवर्ड भूल गए?',

        # Common UI
        'common_loading':     'लोड हो रहा है…',
        'common_error':       'कुछ गलत हो गया।',
        'common_success':     'सफलता!',
        'common_cancel':      'रद्द करें',
        'common_save':        'सहेजें',
        'common_delete':      'हटाएं',
        'common_search':      'खोजें…',

        # Dashboard
        'dashboard_title':         'डैशबोर्ड',
        'dashboard_events':        'मेरे कार्यक्रम',
        'dashboard_registrations': 'पंजीकरण',
        'dashboard_analytics':     'विश्लेषण',
    },

    # ── Kannada ───────────────────────────────────────────────────────────
    'kn': {
        # Navbar
        'nav_home':           'ಮುಖಪುಟ',
        'nav_events':         'ಕಾರ್ಯಕ್ರಮಗಳು',
        'nav_login':          'ಲಾಗಿನ್',
        'nav_logout':         'ಲಾಗ್ಔಟ್',
        'nav_dashboard':      'ಡ್ಯಾಶ್‌ಬೋರ್ಡ್',
        'nav_tickets':        'ನನ್ನ ಟಿಕೆಟ್‌ಗಳು',

        # Hero
        'hero_title':         'ಸಪ್ತ — ಭವ್ಯ ಕಾಲೇಜು ಉತ್ಸವ',
        'hero_subtitle':      'ಪ್ರತಿಭೆ, ಸಂಸ್ಕೃತಿ ಮತ್ತು ನಾವೀನ್ಯತೆಯ ಅಸಾಧಾರಣ ಆಚರಣೆಯನ್ನು ಅನುಭವಿಸಿ.',
        'hero_cta_explore':   'ಕಾರ್ಯಕ್ರಮಗಳನ್ನು ಅನ್ವೇಷಿಸಿ',
        'hero_cta_login':     'ಲಾಗಿನ್ / ನೋಂದಣಿ',

        # Events
        'events_title':       'ವಿಶೇಷ ಕಾರ್ಯಕ್ರಮಗಳು',
        'events_subtitle':    'ಸ್ಪರ್ಧೆಗಳು, ಪ್ರದರ್ಶನಗಳು ಮತ್ತು ಕಾರ್ಯಾಗಾರಗಳ ಜಗತ್ತನ್ನು ಅನ್ವೇಷಿಸಿ.',
        'events_filter_all':       'ಎಲ್ಲಾ',
        'events_filter_technical': 'ತಾಂತ್ರಿಕ',
        'events_filter_cultural':  'ಸಾಂಸ್ಕೃತಿಕ',
        'events_filter_sports':    'ಕ್ರೀಡೆ',

        # Registration
        'register_btn':       'ಈಗ ನೋಂದಾಯಿಸಿ',
        'fee_free':           'ಉಚಿತ',
        'fee_paid':           'ಶುಲ್ಕ',

        # How It Works
        'how_title':          'ಇದು ಹೇಗೆ ಕೆಲಸ ಮಾಡುತ್ತದೆ',
        'how_subtitle':       'ಪ್ರಾರಂಭಿಸುವುದು ಸುಲಭ — ಈ ಸರಳ ಹಂತಗಳನ್ನು ಅನುಸರಿಸಿ.',
        'how_step1':          'ನಿಮ್ಮ ಖಾತೆಯನ್ನು ರಚಿಸಿ ಅಥವಾ ಲಾಗಿನ್ ಮಾಡಿ.',
        'how_step2':          'ನಿಮ್ಮ ಮೆಚ್ಚಿನ ಕಾರ್ಯಕ್ರಮಗಳನ್ನು ಬ್ರೌಸ್ ಮಾಡಿ ಮತ್ತು ಆರಿಸಿ.',
        'how_step3':          'ನೋಂದಾಯಿಸಿ ಮತ್ತು ಪಾವತಿಸಿ (ಅನ್ವಯಿಸಿದರೆ).',
        'how_step4':          'ಸ್ಥಳದಲ್ಲಿ ನಿಮ್ಮ ಇ-ಟಿಕೆಟ್ ತೋರಿಸಿ — ಆನಂದಿಸಿ!',

        # Footer
        'footer_about':       'ಸಪ್ತ ಕುರಿತು',
        'footer_links':       'ತ್ವರಿತ ಲಿಂಕ್‌ಗಳು',
        'footer_contact':     'ನಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸಿ',
        'footer_copyright':   '© 2026 ಸಪ್ತಇವೆಂಟ್ — SNPSU. ಎಲ್ಲ ಹಕ್ಕುಗಳನ್ನು ಕಾಯ್ದಿರಿಸಲಾಗಿದೆ.',

        # Login
        'login_title':        'ಮರಳಿ ಸ್ವಾಗತ',
        'login_email':        'ಇಮೇಲ್ ವಿಳಾಸ',
        'login_password':     'ಗುಪ್ತಪದ',
        'login_submit':       'ಸೈನ್ ಇನ್',
        'login_forgot':       'ಗುಪ್ತಪದ ಮರೆತಿರಾ?',

        # Common UI
        'common_loading':     'ಲೋಡ್ ಆಗುತ್ತಿದೆ…',
        'common_error':       'ಏನೋ ತಪ್ಪಾಯಿತು.',
        'common_success':     'ಯಶಸ್ಸು!',
        'common_cancel':      'ರದ್ದುಮಾಡಿ',
        'common_save':        'ಉಳಿಸಿ',
        'common_delete':      'ಅಳಿಸಿ',
        'common_search':      'ಹುಡುಕಿ…',

        # Dashboard
        'dashboard_title':         'ಡ್ಯಾಶ್‌ಬೋರ್ಡ್',
        'dashboard_events':        'ನನ್ನ ಕಾರ್ಯಕ್ರಮಗಳು',
        'dashboard_registrations': 'ನೋಂದಣಿಗಳು',
        'dashboard_analytics':     'ವಿಶ್ಲೇಷಣೆ',
    },
}
