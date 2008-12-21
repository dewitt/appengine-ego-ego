# Copyright 2008 DeWitt Clinton
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
logging.debug('Beginning main.py')
import os
import re

from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template, Request, Response
from google.appengine.ext.webapp.util import run_wsgi_app

import decorator
import simplejson
import webob
import webob.exc
import wsgidispatcher
from xml.sax.saxutils import escape

CREF_MIMETYPE = 'text/xml'
ANNOTATIONS_MIMETYPE = 'text/xml'
OSD_MIMETYPE = 'application/opensearchdescription+xml'
CACHE_EXPIRATION = 3600
VALID_CSE_RE = re.compile(r'\w+\.[\w\\]+')
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
ANNOTATIONS_URL_TEMPLATE = 'http://ego-ego.appspot.com/friendfeed/%s/annotations/list/'


class ReportableError(Exception):
  """A class of exceptions that should be shown to the user."""
  message = None

  def __init__(self, message):
    """Constructs a new ReportableError.

    Args:
      message: The message to be logged and displayed to the user.
    """
    self.message = message


class UserError(ReportableError):
  """An 400 error caused by user behavior."""


class ServerError(ReportableError):
  """An 500 error caused by the server."""


class RemoteError(ReportableError):
  """An error caused by remote services."""


class TemplateResponse(webob.Response):
  def __init__(self, template_name, template_data=None, *args, **kwargs):
    super(TemplateResponse, self).__init__(*args, **kwargs)
    if template_data is None:
      template_data = {}
    path = os.path.join(TEMPLATE_DIR, template_name)
    self.body = template.render(path, template_data)


def cacheable(keygen=None, expiration=CACHE_EXPIRATION):
  """A decorator that caches results in memcache.
  
  keygen: 
    A function that returns the cache key based on the *args and
    **kwargs of the function being called.  If keygen is 
    not specified, the first positional argument will be used.
  expiration:
    The length of time to cache the response in seconds.
  """
  # Define the decorator itself as a closure within cacheable
  def call(f, *args, **kwargs):
    # Don't use the cache at all if there is no expiration
    if not expiration:
      return f(*args, **kwargs)

    # Use the supplied keygen to create a local cache key
    # or use the first positional arg if none is supplied
    if keygen:
      local_key = keygen(*args, **kwargs)
    else:
      local_key = args[0]

    # Create a global cache key that remains stable across instances
    global_key = '%s:%s:%s' % (f.__module__, f.__name__, local_key)

    logging.debug('Checking cache for %s' % local_key)
    result = memcache.get(global_key)
    if result:
      logging.debug('Found %s in cache.' % local_key)
    else:
      logging.debug('Cache miss for %s' % local_key)
      result = f(*args, **kwargs)
      if result:
        logging.debug('Caching %s' % local_key)
        if not memcache.add(global_key, result, expiration):
          logging.error('Error caching response for %s.' % local_key)
    return result

  return decorator.decorator(call)


def request_keygen(request, *args, **kwargs):
  """Returns a key based on the request path.

  Args:
    request: The http request object.
  """
  if not request or not request.path:
    raise ServerError('First parameter must be a request with a path.')
  return request.path


@cacheable()    
def get_url(url):
  """Retrieves a URL and caches the results.
  
  Args:
    url: A url to be fetched
  Returns:
    a http response
  """
  return urlfetch.fetch(url)


@cacheable()
def get_friendfeed_profile(nickname):
  """Return a friendfeed profile object for a given nickname."""

  if not nickname:
    raise UserError('nickname required')

  friendfeed_profile_url = (
    'http://friendfeed.com/api/user/%s/profile?include=name,nickname,services' % nickname)

  result = get_url(friendfeed_profile_url)
  if result.status_code == 404:
    raise UserError('User %s not found' % nickname)
  elif result.status_code == 401:
    raise UserError('User %s is private' % nickname)
  elif result.status_code != 200:
    raise ServerError('Unknown friendfeed code' % result.status_code)

  friendfeed_profile_json = result.content

  if not friendfeed_profile_json:
    raise ServerError('could not load friendfeed user %s' % nickname)

  logging.debug('Decoding profile for %s' % nickname)
  friendfeed_profile = simplejson.loads(friendfeed_profile_json)
  if not friendfeed_profile:
    raise ServerError('could not parse friendfeed user %s' % nickname)

  return friendfeed_profile


def get_cse_names(friendfeed_profile):
  """Return a list of cse site urls from the profile."""
  cse_names = []
  try:
    services = friendfeed_profile['services']
  except KeyError:
    return cse_names
  for service in services:
    try:
      cse_name = service['profileUrl']
      cse_name = escape(cse_name)
    except KeyError:
      logging.warning('No profileUrl in  %s' % service)
      continue
    if cse_name.startswith('http://'):
      cse_name = cse_name[7:]
    if not VALID_CSE_RE.match(cse_name):
      logging.warning('Invalid cse name for %s' % service)
      continue
    if cse_name.endswith('/'):
      cse_names.append(cse_name)
      cse_names.append(cse_name + '*')
    elif '?' in cse_name:
      cse_names.append(cse_name)
    else:
      cse_names.append(cse_name)
      cse_names.append(cse_name + '/*')
  return cse_names


def get_friendfeed_name(friendfeed_profile, friendfeed_name):
  """Looks into the profile to get the users real name."""
  try:    
    name = friendfeed_profile['name']
  except KeyError:
    try:
      name = friendfeed_profile['nickname']
    except KeyError:
      name = friendfeed_name    
  return name


def get_friend_nicknames(friendfeed_profile):
  """Return a list of friend nicknames from the profile."""
  friend_nicknames = []
  for subscription in friendfeed_profile['subscriptions']:
    try:
      friend_nickname = subscription['nickname']
    except:
      logging.warning('No nickname for %s' % subscription)
      continue
    if not friend_nickname:
      logging.warning('No nickname for %s' % subscription)
      continue
    friend_nicknames.append(friend_nickname.lower())
  return friend_nicknames


def get_annotations(nickname):
  """Retrieve the annotation file for given user."""
  url = ANNOTATIONS_URL_TEMPLATE % nickname
  result = get_url(url)
  if result.status_code != 200:
    logging.debug('Could not load %s' % url)
    annotation = ''
  else:
    return result.content


def NotFoundView(request):
  """Print a 404 page"""
  logging.debug('Beginning NotFound handler')
  return TemplateResponse('404.tmpl', status='404 Not Found')


def ExceptionView(request, *args, **kwargs):
  """Print a 500 page"""
  logging.debug('Beginning ExceptionView handler')
  return TemplateResponse('500.tmpl', status='500 Server Error')


@cacheable(keygen=request_keygen)
def HomeView(request):
  """Prints the wego wego homepage"""
  logging.debug('Beginning HomeView handler')
  return TemplateResponse('home.tmpl')


@cacheable(keygen=request_keygen)
def FaqView(request):
  logging.debug('Beginning FaqView handler')
  return TemplateResponse('faq.tmpl')


def UserRedirectView(request):
  """Redirects a form POST to the user view."""
  logging.debug('Beginning UserRedirectView handler')
  nickname = request.POST.get('nickname')
  if not nickname:
    raise UserError('nickname required')
  return webob.exc.HTTPSeeOther(location=('/friendfeed/%s/' % nickname))


@cacheable(keygen=request_keygen)
def UserView(request, nickname):
  """A request handler that generates a few demos."""
  logging.debug('Beginning UserView handler')
  if not request.path.islower():
    return webob.exc.HTTPMovedPermanently(location=request.path.lower())
  friendfeed_profile = get_friendfeed_profile(nickname)
  name = get_friendfeed_name(friendfeed_profile, nickname)
  template_data = {'nickname': nickname, 'name':  name}
  return TemplateResponse('user.tmpl', template_data)


@cacheable(keygen=request_keygen)
def OsdView(request, nickname):
  """A request handler that generates an opensearch description document."""
  logging.debug('Beginning OsdView handler')
  if not request.path.islower():
    return webob.exc.HTTPMovedPermanently(location=request.path.lower())
  friendfeed_profile = get_friendfeed_profile(nickname)
  name = get_friendfeed_name(friendfeed_profile, nickname)
  template_data = {'nickname': nickname, 'name':  name}
  return TemplateResponse('osd.tmpl', template_data, content_type=OSD_MIMETYPE)



@cacheable(keygen=request_keygen)
def CrefView(request, nickname):
  """A request handler that generates CustomSearch cref files."""
  logging.debug('Beginning CrefView handler')
  if not request.path.islower():
    return webob.exc.HTTPMovedPermanently(location=request.path.lower())
  try:
    friendfeed_profile = get_friendfeed_profile(nickname)
    name = get_friendfeed_name(friendfeed_profile, nickname)
    annotations = get_annotations(nickname)
  except UserError:
    annotations = ''
    nickname = None
    name = None
  template_data = {'nickname': nickname, 'name':  name, 'annotations': annotations}
  return TemplateResponse('cref.tmpl', template_data, content_type=CREF_MIMETYPE)


@cacheable(keygen=request_keygen)
def AnnotationView(request, nickname):
  """A request handler that generates CustomSearch annotation file."""
  logging.debug('Beginning AnnotationView handler')
  if not request.path.islower():
    return webob.exc.HTTPMovedPermanently(location=request.path.lower())
  try:
    annotations = get_annotations(nickname)
  except UserError:
    annotations = ''
  template_data = {'annotations': annotations}
  return TemplateResponse(
    'annotations.tmpl', template_data, content_type=ANNOTATIONS_MIMETYPE)


@cacheable(keygen=request_keygen)
def AnnotationListView(request, nickname):
  """A request handler that generates CustomSearch annotation file."""
  logging.debug('Beginning AnnotationListView handler')
  if not request.path.islower():
    return webob.exc.HTTPMovedPermanently(location=request.path.lower())
  friendfeed_profile = get_friendfeed_profile(nickname)
  cse_names = get_cse_names(friendfeed_profile)
  template_data = {'nickname': nickname, 'cse_names': cse_names}
  return TemplateResponse(
    'annotation_list.tmpl', template_data, content_type=ANNOTATIONS_MIMETYPE)


class Dispatcher(object):
  """A URL dispatcher build on wsgidispatcher.Dispatcher.

  This dispatcher bridges the power of the wsgidispatcher's pattern
  matcher with the convenience of Django style method invocations, with
  little of the overhead of Django.
  """
  def __init__(self):
    self._urls = wsgidispatcher.Dispatcher()
    self._error_handler = None

  def get_app(self):
    """Returns a WSGIApplication instance."""
    return self._urls;

  @staticmethod
  def _redirect_with_slash(environ, start_response):
    """Redirects to the same page with a trailing redirect."""
    new_url = environ['SCRIPT_NAME'] + '/'
    start_response('301 Moved Permanently', 
                   [('content-type', 'text/html'),
                    ('Location', new_url)])
    return [('Page moved to %s' % new_url)]

  class _make_request(object):
    """A private wrapper class around functions to help them support WSGI."""
    def __init__(self, f, error_handler=None):
      self._f = f
      self._error_handler = error_handler

    def __call__(self, environ, start_response):
      request = webob.Request(environ)
      try:
        kwargs = environ['wsgiorg.routing_args'][1]
      except KeyError:
        kwargs = {}
      try:
        response = self._f(request, **kwargs)
      except BaseException, e:
        if self._error_handler:
          return self._error_handler(environ, start_response)
        else:
          raise e
      return response(environ, start_response)

  def add_get_handler(self, path, f, error_handler=None):
    """Add a new route between GET requests to path and the named function.

    The function will be invoked with a webob.Request instance, and
    expect a webob.Response instance to be returned.

    Paths that end with '/' will automatically get a redirector to
    append the missing slash if necessary.
    """
    if error_handler is None:
      error_handler = self._error_handler
    self._urls.add(path, GET=self._make_request(f, error_handler))
    if path.endswith('/'):
      self._urls.add(path[0:-1], GET=self._redirect_with_slash)

  def add_post_handler(self, path, f, error_handler=None):
    """Add a new route between POST requests to path and the named function.

    The function will be invoked with a webob.Request instance, and
    expect a webob.Response instance to be returned.
    """
    if error_handler is None:
      error_handler = self._error_handler
    self._urls.add(path, POST=self._make_request(f, error_handler))

  def add_not_found_handler(self, f):
    self._urls.handle404 = self._make_request(f)

  def add_error_handler(self, f):
    self._error_handler = self._make_request(f)


def Main():
  logging.debug('Beginning Main()')
  dispatcher = Dispatcher()
  if not os.environ['SERVER_SOFTWARE'].startswith('Dev'):
    dispatcher.add_error_handler(ExceptionView)
  dispatcher.add_get_handler('/', HomeView)
  dispatcher.add_get_handler('/faq/', FaqView)
  dispatcher.add_post_handler('/user/', UserRedirectView)
  dispatcher.add_get_handler('/friendfeed/{nickname:word}/', UserView)
  dispatcher.add_get_handler('/friendfeed/{nickname:word}/osd/', OsdView)
  dispatcher.add_get_handler('/friendfeed/{nickname:word}/cref/', CrefView)
  dispatcher.add_get_handler(
    '/friendfeed/{nickname:word}/annotations/', AnnotationView)
  dispatcher.add_get_handler(
    '/friendfeed/{nickname:word}/annotations/list/', AnnotationListView)
  dispatcher.add_not_found_handler(NotFoundView)

  run_wsgi_app(dispatcher.get_app())
  
if __name__ == '__main__':
  Main()
