"""
build_dist.py — Pre-renders Flask Jinja templates into full, static-ready HTML for Zoho Slate deployment
"""

import os
import shutil

def build():
    print("Initializing Flask app for template pre-rendering...")
    from app import app
    
    dist_dir = os.path.join(os.path.dirname(__file__), 'dist')
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir, exist_ok=True)

    # Copy static directory
    static_src = os.path.join(os.path.dirname(__file__), 'static')
    static_dst = os.path.join(dist_dir, 'static')
    if os.path.exists(static_src):
        shutil.copytree(static_src, static_dst, dirs_exist_ok=True)

    # Pre-render public home page inside Flask app context
    with app.app_context(), app.test_request_context('/'):
        try:
            rendered_html = app.jinja_env.get_template('public/home.html').render(
                events=[
                    {
                        'id': 1,
                        'title': 'Fashion Show Extravaganza',
                        'category': 'Cultural',
                        'participation_type': 'Individual',
                        'date': '2026-07-25',
                        'venue': 'Main Auditorium',
                        'registration_count': 142,
                        'limits': {'max_participants': 200},
                        'fees': {'regular': 0}
                    },
                    {
                        'id': 2,
                        'title': 'AI Hackathon 2026',
                        'category': 'Technical',
                        'participation_type': 'Team',
                        'date': '2026-08-15',
                        'venue': 'CS Labs (Zone A)',
                        'registration_count': 48,
                        'limits': {'max_participants': 60},
                        'fees': {'regular': 0}
                    },
                    {
                        'id': 3,
                        'title': 'Football 5-A-Side Cup',
                        'category': 'Sports',
                        'participation_type': 'Team',
                        'date': '2026-07-25',
                        'venue': 'Football Ground',
                        'registration_count': 32,
                        'limits': {'max_participants': 40},
                        'fees': {'regular': 0}
                    }
                ],
                featured_events=[
                    {
                        'title': 'Sapthagiri AI CodeSprint 2026',
                        'category': 'Technical',
                        'participation_type': 'Team',
                        'venue': 'CS Labs'
                    }
                ],
                total_events=17,
                total_regs=2450,
                categories=['Technical', 'Cultural', 'Sports', 'Management', 'Workshop'],
                session={}
            )
            
            with open(os.path.join(dist_dir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(rendered_html)
            print("✅ Successfully pre-rendered templates/public/home.html into dist/index.html!")

        except Exception as e:
            print(f"⚠️ Pre-rendering warning: {e}")

if __name__ == '__main__':
    build()
