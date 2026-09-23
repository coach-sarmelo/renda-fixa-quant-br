.PHONY: help install install-dev test lint format clean

help:
	@echo "Comandos disponíveis:"
	@echo "  install         Instala o pacote em modo editável"
	@echo "  install-dev     Instala com dependências de desenvolvimento"
	@echo "  test            Roda os testes com cobertura"
	@echo "  lint            Roda ruff + mypy"
	@echo "  format          Formata o código com ruff"
	@echo "  clean           Remove artefatos de build e cache"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest

lint:
	ruff check src tests
	mypy src

format:
	ruff check --fix src tests
	ruff format src tests

clean:
	rm -rf build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
