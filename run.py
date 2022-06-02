from funding.factory import create_app
import settings

app = create_app()
app.run(settings.HOST, port=settings.PORT, debug=settings.DEBUG, use_reloader=False)
