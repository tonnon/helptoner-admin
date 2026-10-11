from .local import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Os testes não rodam o collectstatic: o WhiteNoise acha os arquivos em static/, como no
# desenvolvimento, em vez de avisar que a pasta staticfiles/ não existe.
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
