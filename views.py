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

import simplejson

from google.appengine.api import memcache
from google.appengine.api import urlfetch

from django.shortcuts import render_to_response
from django.template.loader import render_to_string
from django import http

from decorator import *

from xml.sax.saxutils import escape

CREF_MIMETYPE = 'text/xml'
ANNOTATIONS_MIMETYPE = 'text/xml'
OSD_MIMETYPE = 'application/opensearchdescription+xml'

CACHE_EXPIRATION = 3600


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
      logging.debug('Cache miss for %s.' % local_key)
      result = f(*args, **kwargs)
      logging.debug('Caching %s' % local_key)
      if not memcache.add(global_key, result, expiration):
        logging.error('Error caching response for %s.' % local_key)
    return result

  return decorator(call)


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
    'http://friendfeed.com/api/user/%s/profile?name,nickname,services' % nickname)

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


def _get_friendfeed_name(friendfeed_profile, friendfeed_name):
  """Looks into the profile to get the users real name."""
  try:    
    name = friendfeed_profile['name']
  except KeyError:
    try:
      name = friendfeed_profile['nickname']
    except KeyError:
      name = friendfeed_name    
  return name


def _get_cse_names(friendfeed_profile):
  """Return a list of cse site urls from the profile."""
  cse_names = []
  for service in friendfeed_profile['services']:
    try:
      cse_name = service['profileUrl']
      cse_name = escape(cse_name)
    except:
      logging.warning('No profile for %s' % service)
      continue
    if cse_name.startswith('http://'):
      cse_name = cse_name[7:]
    if cse_name.endswith('/'):
      cse_names.append(cse_name)
      cse_names.append(cse_name + '*')
    elif '?' in cse_name:
      cse_names.append(cse_name)
    else:
      cse_names.append(cse_name)
      cse_names.append(cse_name + '/*')
  return cse_names


@cacheable(keygen=request_keygen)
def FaqView(request):
  """Prints the FAQ page."""
  logging.debug('Beginning FaqView handler')
  return render_to_response('faq.tmpl')


@cacheable(keygen=request_keygen)
def HomeView(request):
  """Prints the ego ego homepage"""
  logging.debug('Beginning HomeView handler')
  return render_to_response('home.tmpl')


def UserRedirectView(request):
  """Redirects a form POST to the user view."""
  logging.debug('Beginning handler')
  nickname = request.POST.get('nickname')
  if not nickname:
    raise UserError('nickname required')
  return http.HttpResponseRedirect('/friendfeed/%s/' % nickname)


def CrefRedirectView(request):
  """Redirects the old cref URLs to the new view."""
  friendfeed_name = request.GET.get('friendfeed')
  if not friendfeed_name:
    raise UserError('friendfeed nickname required')
  return http.HttpResponsePermanentRedirect('/friendfeed/%s/cref/' % friendfeed_name)


def OsdRedirectView(request):
  """Redirects the old osd URLs to the new view."""
  friendfeed_name = request.GET.get('friendfeed')
  if not friendfeed_name:
    raise UserError('friendfeed nickname required')
  return http.HttpResponsePermanentRedirect('/friendfeed/%s/osd/' % friendfeed_name)


@cacheable(keygen=request_keygen)
def UserView(request, nickname):
  """A request handler that generates a few demos."""
  logging.debug('Beginning UserView handler')

  if not request.path.islower():
    return http.HttpResponseRedirect(request.path.lower())

  friendfeed_profile = get_friendfeed_profile(nickname)
  name = _get_friendfeed_name(friendfeed_profile, nickname)

  template_data = {'nickname': nickname, 'name':  name}

  return render_to_response('user.tmpl', template_data)


@cacheable(keygen=request_keygen)
def CrefView(request, nickname):
  """A request handler that generates CustomSearch cref files."""
  logging.debug('Beginning CrefView handler')

  if not request.path.islower():
    return http.HttpResponseRedirect(request.path.lower())

  try:
    friendfeed_profile = get_friendfeed_profile(nickname)
    name = _get_friendfeed_name(friendfeed_profile, nickname)
    cse_names = _get_cse_names(friendfeed_profile)
  except UserError:
    cse_names = []
    nickname = None
    name = None

  template_data = {'nickname': nickname, 
                   'name':  name,
                   'cse_names': cse_names}

  # Django 0.96's render_to_response does not take a mimetype parameter
  template_string = render_to_string('cref.tmpl', template_data)
  return http.HttpResponse(template_string, mimetype=CREF_MIMETYPE)


@cacheable(keygen=request_keygen)
def AnnotationView(request, nickname, start_index=0):
  """A request handler that generates CustomSearch annotation file."""
  logging.debug('Beginning AnnotationView handler')

  if not request.path.islower():
    return http.HttpResponseRedirect(request.path.lower())

  start_index = int(start_index)
  try:
    friendfeed_profile = get_friendfeed_profile(nickname)
    all_cse_names = _get_cse_names(friendfeed_profile)
  except UserError:
    all_cse_names = []
  end_index = min(len(all_cse_names), start_index + 50)
  cse_names = all_cse_names[start_index:end_index]

  template_data = {'cse_names': cse_names}

  # Django 0.96's render_to_response does not take a mimetype parameter
  template_string = render_to_string('annotations.tmpl', template_data)
  return http.HttpResponse(template_string, mimetype=ANNOTATIONS_MIMETYPE)


@cacheable(keygen=request_keygen)
def OsdView(request, nickname):
  """A request handler that generates an opensearch description document."""
  logging.debug('Beginning OsdView handler')

  if not request.path.islower():
    return http.HttpResponseRedirect(request.path.lower())

  friendfeed_profile = get_friendfeed_profile(nickname)
  name = _get_friendfeed_name(friendfeed_profile, nickname)

  template_data = {'nickname': nickname, 'name':  name}

  # Django 0.96's render_to_response does not take a mimetype parameter
  template_string = render_to_string('osd.tmpl', template_data)
  return http.HttpResponse(template_string, mimetype=OSD_MIMETYPE)

