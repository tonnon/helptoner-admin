from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@login_not_required
@require_GET
def saude(request):
    """Página de saúde: não toca em usuário, sessão nem banco."""
    return JsonResponse({"status": "ok"})
