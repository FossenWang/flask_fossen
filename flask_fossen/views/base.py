from flask import request, abort
from flask.views import View, MethodView
from sqlalchemy.orm.exc import NoResultFound



class BaseView(View):
    """Basic view for dispatching diffirent http method."""
    allowed_http_method = ['get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace']

    def dispatch_request(self, *args, **kwargs):
        # Try to dispatch to the right method; if a method doesn't exist,
        # defer to the error handler. Also defer to the error handler if the
        # request method isn't on the approved list.
        self.args = args
        self.kwargs = kwargs
        if request.method.lower() in self.allowed_http_method:
            handler = getattr(self, request.method.lower(), self.http_method_not_allowed)
        else:
            handler = self.http_method_not_allowed
        return handler(*args, **kwargs)

    def http_method_not_allowed(self, *args, **kwargs):
        abort(405)


class ContextMixin:
    """
    A default context mixin that passes the keyword arguments received by
    get_context_data() as context data.
    """
    extra_context = None

    def get_context_data(self, **kwargs):
        if self.extra_context is not None:
            kwargs.update(self.extra_context)
        return kwargs


class SingleObjectMixin:
    """
    Provide the ability to retrieve a single object for further manipulation.
    """
    model = None
    query = None
    id_url_kwarg = 'id'
    # context_object_name = 'object'

    def get_query(self):
        """
        Return the `query` that will be used to look up the object.

        This method is called by the default implementation of get_object() and
        may not be called if get_object() is overridden.
        """
        if self.query is None:
            if self.model:
                return self.model.query
            else:
                raise ValueError(
                    "%(cls)s is missing a query. Define "
                    "%(cls)s.model, %(cls)s.query, or override "
                    "%(cls)s.get_query()." % {
                        'cls': self.__class__.__name__
                    }
                )
        return self.query

    def get_object(self, query=None):
        """
        Return the object the view is displaying.

        Require `self.query` and a `id` argument in the URLconf.
        Subclasses can override this to return any object.
        """
        # Use a custom query if provided; this is required for subclasses
        if query is None:
            query = self.get_query()

        # Next, try looking up by primary key.
        obj_id = self.kwargs.get(self.id_url_kwarg)
        if obj_id is not None:
            query = query.filter(self.model.id==obj_id)
        else:
            raise AttributeError("No object id")

        try:
            # Get the single item from the filtered query
            obj = query.one()
        except NoResultFound:
            raise abort(404)
        return obj

    '''def get_context_object_name(self, obj):
        """Get the name to use for the object."""
        if self.context_object_name:
            return self.context_object_name
        else:
            return obj.__class__.__name__.lower()

    def get_context_data(self, **kwargs):
        """Insert the single object into the context dict."""
        context = {}
        if self.object:
            context_object_name = self.get_context_object_name(self.object)
            context[context_object_name] = self.object
        context.update(kwargs)
        return super().get_context_data(**context)'''


class CreateMixin:
    """Create a single object."""
    def post(self, *args, **kwargs):
        form = self.get_form()
        if form.validate():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_form(self):
        pass

    def form_valid(self, form):
        pass
    
    def form_invalid(self, form):
        pass

