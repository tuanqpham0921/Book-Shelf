# -------------------
# Local dev
# -------------------

.PHONY: install
install:
	npm install

# serves on :3000 against http://localhost:8000 (.env.development)
.PHONY: dev
dev:
	npm run dev

.PHONY: lint
lint:
	npm run lint

# -------------------
# Deploy
# -------------------

# Vite runs this in production mode, so VITE_API_URL comes from .env.production
# — the Cloud Run URL is in the repo, which is what makes the build
# reproducible: no local .env to forget, nothing to pass on the command line.
.PHONY: build
build:
	npm run build

# build + publish dist/ to Firebase Hosting (target book-rec -> tuanqpham0921)
.PHONY: deploy
deploy: build
	firebase deploy --only hosting
	@echo "Live at https://tuanqpham0921.web.app"
