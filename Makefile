SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := up

.PHONY: up down rebuild

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

rebuild:
	$(COMPOSE) down
	$(COMPOSE) up -d --build
