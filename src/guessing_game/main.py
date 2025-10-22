#!/usr/bin/env python3
"""
Main entry point for the SLIM Guessing Game.

This module provides the CLI interface for different agent roles in the game.
"""

import os
import click


@click.group()
@click.version_option()
@click.option('--log-level', default='INFO', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
              help='Set logging level')
def cli(log_level):
    """ SLIM Guessing Game - Educational AI Agent Game for Children! 
    
    A fun game where LLM-powered AI agents play "20 Questions" together using secure messaging.
    Powered by LLM intelligence - no internet required!
    
    Roles:
    - coordinator: Manages the game flow and rules
    - thinker: Uses LLM to think of objects and answer questions intelligently
    - guesser: Uses LLM to ask strategic questions and make educated guesses
    """
    # Set log level in environment for all subprocesses
    os.environ['LOG_LEVEL'] = log_level.upper()


@cli.command()
@click.option('--slim', default='{"endpoint":"http://slim.slim.svc.cluster.local:46357","tls":{"insecure":true}}', 
              help='SLIM connection configuration as JSON')
@click.option('--shared-secret', default='secret123', help='Shared secret for authentication')
@click.option('--game-channel', default='school/classroom/guessing-game', help='Game channel name')
@click.option('--max-questions', default=20, help='Maximum questions allowed')
@click.option('--max-guesses', default=3, help='Maximum final guesses allowed')
def coordinator(slim, shared_secret, game_channel, max_questions, max_guesses):
    """ Run the game coordinator - manages game flow and rules."""
    from .game_coordinator import coordinator_main
    coordinator_main(slim, shared_secret, game_channel, max_questions, max_guesses)


@cli.command() 
@click.option('--slim', default='{"endpoint":"http://slim.slim.svc.cluster.local:46357","tls":{"insecure":true}}',
              help='SLIM connection configuration as JSON')
@click.option('--shared-secret', default='secret123', help='Shared secret for authentication')
@click.option('--game-channel', default='school/classroom/guessing-game', help='Game channel name')
@click.option('--agent-name', required=True, help='Name of this thinker agent (e.g., Alice)')
def thinker(slim, shared_secret, game_channel, agent_name):
    """ Run a thinker agent - thinks of objects and answers questions using LLM."""
    from .thinker_agent import thinker_main
    thinker_main(slim, shared_secret, game_channel, agent_name)


@cli.command()
@click.option('--slim', default='{"endpoint":"http://slim.slim.svc.cluster.local:46357","tls":{"insecure":true}}',
              help='SLIM connection configuration as JSON')
@click.option('--shared-secret', default='secret123', help='Shared secret for authentication') 
@click.option('--game-channel', default='school/classroom/guessing-game', help='Game channel name')
@click.option('--agent-name', required=True, help='Name of this guesser agent (e.g., Bob, Carol, Dave)')
@click.option('--strategy', default='random', type=click.Choice(['random', 'systematic', 'creative']),
              help='LLM personality strategy to use')
def guesser(slim, shared_secret, game_channel, agent_name, strategy):
    """ Run a guesser agent - asks questions and tries to guess objects using LLM."""
    from .guesser_agent import guesser_main
    guesser_main(slim, shared_secret, game_channel, agent_name, strategy)


@cli.command()
@click.option('--slim', default='{"endpoint":"http://slim.slim.svc.cluster.local:46357","tls":{"insecure":true}}',
              help='SLIM connection configuration as JSON')
@click.option('--shared-secret', default='secret123', help='Shared secret for authentication')
@click.option('--game-channel', default='school/classroom/guessing-game', help='Game channel name')
@click.option('--agent-name', default='Travis', help='Name of this translator agent')
@click.option('--target-language', default='Hungarian', help='Target language for translation (e.g., Spanish, French, German)')
def translator(slim, shared_secret, game_channel, agent_name, target_language):
    """Run a translator observer - translates all game messages to a specified language using LLM."""
    from .translator_agent import translator_main
    translator_main(slim, shared_secret, game_channel, agent_name, target_language)


if __name__ == '__main__':
    cli()
