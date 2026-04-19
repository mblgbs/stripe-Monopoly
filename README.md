# stripe-Monopoly

Microservice FastAPI minimal pour **Stripe Checkout** (sessions), **Payment Links** (lien de paiement réutilisable hébergé par Stripe) et **webhooks** (`checkout.session.completed`).

- **Checkout** : flux où ton front appelle l’API puis redirige vers une session Checkout (URLs success/cancel dans `.env`).
- **Payment Link** : l’API renvoie une URL Stripe à partager ; après paiement, redirection vers `CHECKOUT_SUCCESS_URL` (même variable que pour le succès Checkout).

**Écosystème :** découverte des URLs des autres microservices — `GET http://127.0.0.1:8004/ecosystem` ([README services-Monopoly-](../services-Monopoly-/README.md#decouverte-des-services-ecosystem)) ; ce service utilise le port **8006** en local.

## Prérequis

- Python 3.10+
- Compte Stripe (mode test recommandé pour le développement local)
- [Stripe CLI](https://stripe.com/docs/stripe-cli) pour recevoir les webhooks en local

## Installation

```powershell
cd "H:\Mon Drive\stripe-Monopoly"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Renseigner `.env` :

- `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` : clés test du [Dashboard](https://dashboard.stripe.com/test/apikeys)
- `STRIPE_PRICE_ID` : un prix créé sous **Produits** (montant ponctuel ou autre)
- `CHECKOUT_SUCCESS_URL` / `CHECKOUT_CANCEL_URL` : URLs absolues (pages statiques ou ton front)

## Lancer l’API

Port local recommandé : **8006** (8005 est utilisé par `sncf-connect-Monopoly`).

```powershell
$env:PORT="8006"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8006
```

## Webhooks en local (Stripe CLI)

Dans un second terminal :

```powershell
stripe listen --forward-to http://127.0.0.1:8006/webhook
```

La commande affiche un **secret de signing** du type `whsec_...` : copie-le dans `STRIPE_WEBHOOK_SECRET` de ton `.env` pour que la vérification de signature réussisse.

## Endpoints

| Méthode | Chemin | Description |
|--------|--------|-------------|
| `GET` | `/health` | Santé du service |
| `POST` | `/checkout/session` | Crée une session Checkout ; réponse JSON `{"url": "..."}` pour rediriger le navigateur |
| `POST` | `/payment-links` | Crée un Payment Link ; réponse JSON `{"url": "..."}` (lien public à partager) |
| `POST` | `/webhook` | Endpoint Stripe (corps brut + en-tête `Stripe-Signature`) |

## Tests

```powershell
python -m pytest tests/ -v
```

Les tests mockent le SDK Stripe (aucun appel réseau).

## Convention de ports (écosystème Monopoly)

Référence : [`services-Monopoly-/README.md`](../services-Monopoly-/README.md). Ce service utilise **8006**.
