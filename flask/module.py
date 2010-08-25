# -*- coding: utf-8 -*-
"""
    flask.module
    ~~~~~~~~~~~~

    Implements a class that represents module blueprints.

    :copyright: (c) 2010 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""

import os
from .helpers import _PackageBoundObject, _endpoint_from_view_func


def _register_module(module):
    """Internal helper function that returns a function for recording
    that registers the `send_static_file` function for the module on
    the application if necessary.  It also registers the module on
    the application.
    """
    def _register(state):
        state.app.modules[module.name] = module
        path = module.static_path
        # XXX: backwards compatibility.  This will go away in 1.0
        if module._backwards_compat_static_path:
            if path == state.app.static_path:
                return
            from warnings import warn
            warn(DeprecationWarning('With Flask 0.7 the static folder '
                'for modules became explicit due to problems with the '
                'existing system on Google App Engine and multiple '
                'modules with the same prefix.\n'
                'Pass ``static_path=\'static\'`` to the Module '
                'constructor if you want to use static folders.\n'
                'This backwards compatibility support will go away in '
                'Flask 1.0'), stacklevel=2)
        if path is None:
            return
        path = '/' + os.path.basename(path)
        if state.url_prefix:
            path = state.url_prefix + path
        state.app.add_url_rule(path + '/<path:filename>',
                               endpoint='%s.static' % module.name,
                               view_func=module.send_static_file,
                               subdomain=module.subdomain)
        # overriding pre-defined static rule
        if not module.url_prefix and not module.subdomain:
            state.app.static_path = None
            state.app.view_functions['static'] = module.send_static_file
    return _register


class _ModuleSetupState(object):

    def __init__(self, app, url_prefix=None, subdomain=None):
        self.app = app
        self.url_prefix = url_prefix
        self.subdomain = subdomain


class Module(_PackageBoundObject):
    """Container object that enables pluggable applications.  A module can
    be used to organize larger applications.  They represent blueprints that,
    in combination with a :class:`Flask` object are used to create a large
    application.

    A module is like an application bound to an `import_name`.  Multiple
    modules can share the same import names, but in that case a `name` has
    to be provided to keep them apart.  If different import names are used,
    the rightmost part of the import name is used as name.

    Here's an example structure for a larger application::

        /myapplication
            /__init__.py
            /views
                /__init__.py
                /admin.py
                /frontend.py

    The `myapplication/__init__.py` can look like this::

        from flask import Flask
        from myapplication.views.admin import admin
        from myapplication.views.frontend import frontend

        app = Flask(__name__)
        app.register_module(admin, url_prefix='/admin')
        app.register_module(frontend)

    And here's an example view module (`myapplication/views/admin.py`)::

        from flask import Module

        admin = Module(__name__)

        @admin.route('/')
        def index():
            pass

        @admin.route('/login')
        def login():
            pass

    For a gentle introduction into modules, checkout the
    :ref:`working-with-modules` section.

    .. versionadded:: 0.5
       The `static_path` parameter was added and it's now possible for
       modules to refer to their own templates and static files.  See
       :ref:`modules-and-resources` for more information.

    .. versionadded:: 0.6
       The `subdomain` parameter was added.

    :param import_name: the name of the Python package or module
                        implementing this :class:`Module`.
    :param name: the internal short name for the module.  Unless specified
                 the rightmost part of the import name
    :param url_prefix: an optional string that is used to prefix all the
                       URL rules of this module.  This can also be specified
                       when registering the module with the application.
    :param subdomain: used to set the subdomain setting for URL rules that
                      do not have a subdomain setting set.
    :param static_path: when specified this points to a folder (relative to
                        the module's root path) that is exposed on the web.
                        By default nothing is exposed although for backwards
                        compatibility with older versions of Flask it will
                        check if a folder named "static" exists and
                        automatically set the `static_path` to ``'static'``
                        if it finds a folder with that name.  This
                        functionality however is deprecated and will
                        vanish in Flask 1.0.
    """
    _backwards_compat_static_path = False

    def __init__(self, import_name, name=None, url_prefix=None,
                 static_path=None, subdomain=None):
        if name is None:
            assert '.' in import_name, 'name required if package name ' \
                'does not point to a submodule'
            name = import_name.rsplit('.', 1)[1]
        _PackageBoundObject.__init__(self, import_name, static_path)
        self.name = name
        self.url_prefix = url_prefix
        self.subdomain = subdomain
        self._register_events = [_register_module(self)]

        # XXX: backwards compatibility, see _register_module.  This
        # will go away in 1.0
        if self.static_path is None:
            path = os.path.join(self.root_path, 'static')
            if os.path.isdir(path):
                self.static_path = path
                self._backwards_compat_static_path = True

    def route(self, rule, **options):
        """Like :meth:`Flask.route` but for a module.  The endpoint for the
        :func:`url_for` function is prefixed with the name of the module.
        """
        def decorator(f):
            self.add_url_rule(rule, f.__name__, f, **options)
            return f
        return decorator

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        """Like :meth:`Flask.add_url_rule` but for a module.  The endpoint for
        the :func:`url_for` function is prefixed with the name of the module.

        .. versionchanged:: 0.6
           The `endpoint` argument is now optional and will default to the
           function name to consistent with the function of the same name
           on the application object.
        """
        def register_rule(state):
            the_rule = rule
            if state.url_prefix:
                the_rule = state.url_prefix + rule
            options.setdefault('subdomain', state.subdomain)
            the_endpoint = endpoint
            if the_endpoint is None:
                the_endpoint = _endpoint_from_view_func(view_func)
            state.app.add_url_rule(the_rule, '%s.%s' % (self.name,
                                                        the_endpoint),
                                   view_func, **options)
        self._record(register_rule)

    def before_request(self, f):
        """Like :meth:`Flask.before_request` but for a module.  This function
        is only executed before each request that is handled by a function of
        that module.
        """
        self._record(lambda s: s.app.before_request_funcs
            .setdefault(self.name, []).append(f))
        return f

    def before_app_request(self, f):
        """Like :meth:`Flask.before_request`.  Such a function is executed
        before each request, even if outside of a module.
        """
        self._record(lambda s: s.app.before_request_funcs
            .setdefault(None, []).append(f))
        return f

    def after_request(self, f):
        """Like :meth:`Flask.after_request` but for a module.  This function
        is only executed after each request that is handled by a function of
        that module.
        """
        self._record(lambda s: s.app.after_request_funcs
            .setdefault(self.name, []).append(f))
        return f

    def after_app_request(self, f):
        """Like :meth:`Flask.after_request` but for a module.  Such a function
        is executed after each request, even if outside of the module.
        """
        self._record(lambda s: s.app.after_request_funcs
            .setdefault(None, []).append(f))
        return f

    def context_processor(self, f):
        """Like :meth:`Flask.context_processor` but for a module.  This
        function is only executed for requests handled by a module.
        """
        self._record(lambda s: s.app.template_context_processors
            .setdefault(self.name, []).append(f))
        return f

    def app_context_processor(self, f):
        """Like :meth:`Flask.context_processor` but for a module.  Such a
        function is executed each request, even if outside of the module.
        """
        self._record(lambda s: s.app.template_context_processors
            .setdefault(None, []).append(f))
        return f

    def app_errorhandler(self, code):
        """Like :meth:`Flask.errorhandler` but for a module.  This
        handler is used for all requests, even if outside of the module.

        .. versionadded:: 0.4
        """
        def decorator(f):
            self._record(lambda s: s.app.errorhandler(code)(f))
            return f
        return decorator

    def _record(self, func):
        self._register_events.append(func)
