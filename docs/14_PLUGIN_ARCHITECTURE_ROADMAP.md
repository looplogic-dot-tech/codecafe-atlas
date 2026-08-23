# Plugin Architecture Roadmap

This is a future direction, not current v1.0.24.23 implementation.

## Motivation

Several current modules are intentionally specialized and should not be forced onto unrelated organizations.

First replaceable module families:
- document generator / service orders;
- PDF separator/processor;
- counter/meter registry.

Possible additional plugins:
- invoicing;
- quotations;
- ERP functions;
- custom maintenance workflows.

## Desired boundary

Atlas Core should expose stable services:
- organizations/buildings/dependencies;
- people;
- equipment;
- authentication/authorization in Web;
- storage;
- logging;
- backups;
- plugin configuration.

Plugins should not depend directly on raw SQLite table names when avoidable. A stable internal API makes later database/web changes survivable.

## Plugin manifest concept

A future plugin should declare:
- plugin ID/version;
- compatible Atlas API version;
- navigation entry;
- requested capabilities;
- entities read/written;
- files generated/consumed;
- configuration UI.

This roadmap must not be implemented by allowing arbitrary untrusted Python execution without a security model.
