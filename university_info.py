"""
university_info.py — facts about Sapthagiri NPS University that the home page
shows (UPG-86).

Every value here was taken from the university's own website,
https://snpsu.edu.in, on 2026-10-12 (links checked to open a real page, not the
site's catch-all home page). When the university's site changes, change it
here; nothing on the home page is invented or counted by hand.
"""

SOURCE_URL = 'https://snpsu.edu.in'
CHECKED_ON = '2026-10-12'

UNIVERSITY = {
    'name': 'Sapthagiri NPS University',
    'short': 'SNPSU',
    'tagline': 'Where Education Creates Professionals.',
    'city': 'Bengaluru',
    'address': '#14/5, Chikkasandra, Hesarghatta Main Road, Bengaluru 560057',
    'phones': [('080-28 372800', 'tel:+918028372800'), ('+91 99000 72632', 'tel:+919900072632')],
    'email': 'admissions@snpsu.edu.in',
    'whatsapp': 'https://wa.me/919035922194',
    'website': 'https://snpsu.edu.in',

    # Official accounts, as linked from the university's home page
    'social': [
        {'name': 'Instagram', 'icon': 'fa-instagram', 'handle': '@sapthagirinpsuniversity',
         'url': 'https://www.instagram.com/sapthagirinpsuniversity/'},
        {'name': 'YouTube', 'icon': 'fa-youtube', 'handle': '@SapthagiriNPSUniversity',
         'url': 'https://www.youtube.com/@SapthagiriNPSUniversity'},
        {'name': 'LinkedIn', 'icon': 'fa-linkedin-in', 'handle': 'Sapthagiri NPS University',
         'url': 'https://www.linkedin.com/company/sapthagiri-nps-university'},
        {'name': 'Facebook', 'icon': 'fa-facebook-f', 'handle': 'snpsuofficial',
         'url': 'https://www.facebook.com/snpsuofficial'},
        {'name': 'X', 'icon': 'fa-x-twitter', 'handle': '@sapthagirinps',
         'url': 'https://x.com/sapthagirinps'},
    ],

    # The schools and their programmes, as the university lists them
    'schools': [
        {'name': 'School of Engineering & Technology', 'icon': 'fa-microchip',
         'programmes': ['6 undergraduate (B.Tech)', '3 postgraduate (M.Tech)']},
        {'name': 'School of Management Studies', 'icon': 'fa-chart-line',
         'programmes': ['9 undergraduate (BBA, B.Com)', 'MBA with 6 specialisations']},
        {'name': 'School of Applied Sciences', 'icon': 'fa-laptop-code',
         'programmes': ['4 undergraduate (BCA)', '4 postgraduate (MCA)']},
        {'name': 'School of Medicine & Health Sciences', 'icon': 'fa-stethoscope',
         'programmes': ['MBBS', '20 postgraduate (MD/MS)', '6 super-speciality (DM/M.Ch)',
                        '13 allied health programmes']},
    ],

    # Statements the university makes about itself on its home page
    'highlights': [
        {'icon': 'fa-hospital', 'title': 'Sapthagiri Hospital',
         'text': 'Part of the university alongside its four schools.'},
        {'icon': 'fa-globe', 'title': '19 international partners',
         'text': 'Collaborations listed by the university include Cambridge, the University of Lincoln and Colorado State University.'},
        {'icon': 'fa-handshake', 'title': 'Industry MoUs',
         'text': 'Microsoft, IBM, Bosch Rexroth, Schneider and EDuNET.'},
        {'icon': 'fa-certificate', 'title': 'ISO 9001:2015',
         'text': 'Certified quality management system.'},
        {'icon': 'fa-lightbulb', 'title': 'Centre for Innovation Leadership',
         'text': 'Training in emerging technologies, alongside programme add-on labs.'},
        {'icon': 'fa-masks-theater', 'title': 'Arts and sport',
         'text': 'A Centre for Performing Arts, sports, yoga and gym facilities.'},
    ],

    # Pages on the university's site (each opens a real page)
    'links': [
        {'label': 'Admissions 2026–27', 'url': 'https://snpsu.edu.in/admission'},
        {'label': 'Apply online', 'url': 'https://admission.snpsu.edu.in/'},
        {'label': 'Brochure', 'url': 'https://snpsu.edu.in/view-pdf/brochure'},
        {'label': 'University events calendar', 'url': 'https://snpsu.edu.in/events-list'},
        {'label': 'News', 'url': 'https://snpsu.edu.in/news-list'},
        {'label': 'Photo gallery', 'url': 'https://snpsu.edu.in/gallery-category'},
        {'label': 'Results', 'url': 'https://snpsu.edu.in/results'},
        {'label': 'Contact', 'url': 'https://snpsu.edu.in/contact_us'},
    ],
}
