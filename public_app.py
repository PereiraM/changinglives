#!/usr/bin/env python

import datetime
import logging
import os
import re
import shlex
import subprocess
import time
import urllib

from flask import Flask, redirect, render_template
from jinja2.filters import escape, do_mark_safe
from tumblpy import Tumblpy
from tumblpy import TumblpyError
from werkzeug import secure_filename

import app_config

app = Flask(app_config.PROJECT_NAME)
app.config['PROPAGATE_EXCEPTIONS'] = True

os.environ['TZ'] = 'US/Eastern'
time.tzset()

logger = logging.getLogger('tumblr')
file_handler = logging.FileHandler('/var/log/%s.log' % app_config.PROJECT_SLUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)


@app.route('/%s/' % app_config.PROJECT_SLUG, methods=['POST'])
def _post_to_tumblr():
    """
    Handles the POST to Tumblr.
    """
    def strip_html(value):
        """
        Strips HTML from a string.
        """
        return re.compile(r'</?\S([^=]*=(\s*"[^"]*"|\s*\'[^\']*\'|\S*)|[^>])*?>', re.IGNORECASE).sub('', value)

    def strip_breaks(value):
        """
        Converts newlines, returns and other breaks to <br/>.
        """
        value = re.sub(r'\r\n|\r|\n', '\n', value)
        return value.replace('\n', do_mark_safe('<br/>'))

    # Request is a global. Import it down here where we need it.
    from flask import request

    # These should match the form fields.
    message = strip_html(request.form.get('message', None))
    message = escape(message)
    message = strip_breaks(message)

    name = strip_html(request.form.get('signed_name', None))

    svg = request.form.get('image', None)

    file_path = '/uploads/%s/%s_%s' % (
        app_config.PROJECT_SLUG,
        str(time.mktime(datetime.datetime.now().timetuple())).replace('.', ''),
        secure_filename(name.replace(' ', '-'))
    )

    svg_path = file_path + '.svg'
    png_path = file_path + '.png'

    with open('/var/www%s' % svg_path, 'wb') as f:
        f.write(svg.encode('utf-8'))

    command = '/home/ubuntu/apps/changing-lives/virtualenv/bin/cairosvg /var/www%s -f png -o /var/www%s' % (svg_path, png_path)
    logger.info(command)
    args = shlex.split(command)
    subprocess.call(args)

    context = {
        'message': message,
        'message_urlencoded': urllib.quote(message),
        'name': name,
        'app_config': app_config,
        'image_url_urlencoded': urllib.quote('http://%s%s' % (app_config.SERVERS[0], png_path))
    }

    caption = render_template('caption.html', **context)

    secrets = app_config.get_secrets()

    t = Tumblpy(
        app_key=secrets['TUMBLR_APP_KEY'],
        app_secret=secrets['TUMBLR_APP_SECRET'],
        oauth_token=secrets['TUMBLR_OAUTH_TOKEN'],
        oauth_token_secret=secrets['TUMBLR_OAUTH_TOKEN_SECRET'])
    
    logger.info(secrets['TUMBLR_APP_KEY'])
    logger.info("http://%s%s" % (app_config.SERVERS[0], png_path))

    params = {
        "type": "photo",
        "caption": caption,
        "tags": app_config.TUMBLR_TAGS,
        "source": "http://%s%s" % (app_config.SERVERS[0], png_path)
    }

    try:
        tumblr_post = t.post('post', blog_url=app_config.TUMBLR_URL, params=params)
        tumblr_url = u"http://%s/%s" % (app_config.TUMBLR_URL, tumblr_post['id'])
        logger.info('200 %s reader(%s) (times in EST)' % (tumblr_url, name))

        return redirect(tumblr_url, code=301)

    except TumblpyError, e:
        logger.error('%s %s http://%s%s reader(%s) (times in EST)' % (
            e.error_code, e.msg, app_config.SERVERS[0], svg_path, name))
        return 'TUMBLR ERROR'

    return redirect('%s#posts' % tumblr_url, code=301)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8001, debug=app_config.DEBUG)
