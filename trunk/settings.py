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

"""Django settings for the Ego Ego project."""

import os

ROOT_URLCONF = 'urls'

DEBUG = os.environ['SERVER_SOFTWARE'].startswith('Dev')

TEMPLATE_CONTEXT_PROCESSORS = (
    "django.core.context_processors.debug",
    "django.core.context_processors.i18n",
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    )

TEMPLATE_DIRS = (
    os.path.join(os.path.dirname(__file__), 'templates'),
    )
