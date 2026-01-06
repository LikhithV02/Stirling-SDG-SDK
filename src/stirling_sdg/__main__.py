"""CLI interface for Stirling PDF Synthetic Data Generator."""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .config.settings import Settings
from .pipeline.orchestrator import PipelineOrchestrator
from .pipeline.config_manager import ConfigManager
from .utils.logging_utils import setup_logging, get_logger

console = Console()
logger = get_logger(__name__)


@click.group()
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    help="Logging level",
)
def cli(log_level):
    """Stirling PDF Synthetic Data Generator.

    Generate synthetic data PDFs using Stirling PDF API and Groq LLM.
    """
    setup_logging(log_level=log_level.upper())


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    required=True,
    help="Output PDF path",
)
@click.option(
    "--save-template",
    is_flag=True,
    help="Save classification template for reuse",
)
def process(input_path, output, save_template):
    """Process a single document to generate synthetic data PDF.

    \b
    Example:
        stirling-sdg process input.pdf --output output.pdf --save-template
    """
    try:
        settings = Settings()
        orchestrator = PipelineOrchestrator(settings)

        with console.status(
            f"[bold green]Processing {input_path.name}...", spinner="dots"
        ):
            result = orchestrator.process_single(
                input_path, output, save_template=save_template
            )

        console.print(f"\n[green]✓ Success![/green] Generated: {result}")

        if save_template:
            template_name = f"{input_path.stem}_template.json"
            console.print(
                f"[blue]Template saved:[/blue] configs/templates/{template_name}"
            )

    except Exception as e:
        console.print(f"\n[red]✗ Error:[/red] {e}", style="bold red")
        logger.exception("Processing failed")
        raise click.Abort()


@cli.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory for generated PDFs",
)
@click.option(
    "--num",
    "-n",
    type=int,
    default=10,
    help="Number of variations to generate (default: 10)",
)
@click.option(
    "--template",
    "-t",
    type=click.Path(exists=True, path_type=Path),
    help="Pre-saved template (skips classification)",
)
def batch(input_path, output_dir, num, template):
    """Generate multiple variations with template reuse.

    \b
    Example:
        stirling-sdg batch input.pdf --output-dir ./output --num 100
        stirling-sdg batch input.pdf -o ./output -n 50 -t template.json
    """
    try:
        settings = Settings()
        orchestrator = PipelineOrchestrator(settings)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        with console.status(
            f"[bold green]Generating {num} variations...", spinner="dots"
        ):
            results = orchestrator.process_batch(
                input_path, output_dir, num_variations=num, template_path=template
            )

        console.print(
            f"\n[green]✓ Success![/green] Generated {len(results)}/{num} variations"
        )
        console.print(f"[blue]Output directory:[/blue] {output_dir}")

        if len(results) < num:
            console.print(
                f"\n[yellow]Warning:[/yellow] {num - len(results)} variations failed",
                style="yellow",
            )

    except Exception as e:
        console.print(f"\n[red]✗ Error:[/red] {e}", style="bold red")
        logger.exception("Batch processing failed")
        raise click.Abort()


@cli.command()
@click.option(
    "--template",
    "-t",
    type=str,
    required=True,
    help="Template name (without _template.json suffix)",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    required=True,
    help="Output directory for generated PDFs",
)
@click.option(
    "--num",
    "-n",
    type=int,
    default=10,
    help="Number of variations to generate (default: 10)",
)
def batch_from_template(template, output_dir, num):
    """Generate variations using a saved template (faster).

    \b
    Example:
        stirling-sdg batch-from-template -t medical_form -o ./output -n 100
    """
    try:
        settings = Settings()
        config_manager = ConfigManager(settings)

        # Load the template
        template_data = config_manager.load_template(template)

        # Need the original PDF path (stored in template metadata if available)
        # For now, show error message
        console.print(
            "[yellow]Note:[/yellow] batch-from-template requires original PDF path",
            style="yellow",
        )
        console.print(
            "Use: stirling-sdg batch <input.pdf> -o <output_dir> -n <num> -t <template.json>"
        )

    except FileNotFoundError as e:
        console.print(f"\n[red]✗ Error:[/red] {e}", style="bold red")
        console.print(
            f"\nAvailable templates: {', '.join(config_manager.list_templates())}"
        )
        raise click.Abort()
    except Exception as e:
        console.print(f"\n[red]✗ Error:[/red] {e}", style="bold red")
        logger.exception("Template-based generation failed")
        raise click.Abort()


@cli.command()
def init_config():
    """Initialize default pipeline configuration.

    Creates a default pipeline config in configs/pipeline_templates/default.yaml
    """
    try:
        settings = Settings()
        config_manager = ConfigManager(settings)

        config = config_manager.create_default_pipeline()

        console.print(
            "[green]✓ Default pipeline config created![/green]",
            style="bold green",
        )
        console.print(
            f"[blue]Location:[/blue] {settings.config_dir}/pipeline_templates/default.yaml"
        )
        console.print("\n[bold]Configuration:[/bold]")
        console.print(f"  Name: {config['name']}")
        console.print(f"  Batch variations: {config['batch']['num_variations']}")

    except Exception as e:
        console.print(f"\n[red]✗ Error:[/red] {e}", style="bold red")
        raise click.Abort()


@cli.command()
def list_templates():
    """List available classification templates."""
    try:
        settings = Settings()
        config_manager = ConfigManager(settings)

        templates = config_manager.list_templates()

        if not templates:
            console.print(
                "[yellow]No templates found.[/yellow] Create one with --save-template"
            )
            return

        table = Table(title="Available Templates", show_header=True)
        table.add_column("Template Name", style="cyan")
        table.add_column("Location", style="blue")

        for name in templates:
            location = f"configs/templates/{name}_template.json"
            table.add_row(name, location)

        console.print(table)

    except Exception as e:
        console.print(f"\n[red]✗ Error:[/red] {e}", style="bold red")
        raise click.Abort()


@cli.command()
def info():
    """Display current configuration and system info."""
    try:
        settings = Settings()

        table = Table(title="Stirling PDF SDG Configuration", show_header=True)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="green")

        # API Settings
        table.add_row("Stirling PDF URL", settings.stirling_pdf_url)
        table.add_row(
            "Stirling API Key",
            "***" + settings.stirling_api_key[-4:]
            if settings.stirling_api_key
            else "Not set",
        )
        table.add_row("Groq Model", settings.groq_model)

        # Processing Settings
        table.add_row("OCR Languages", settings.ocr_languages)
        table.add_row("Classification Temperature", str(settings.classification_temperature))
        table.add_row("Synthesis Temperature", str(settings.synthesis_temperature))

        # Paths
        table.add_row("Input Directory", str(settings.input_dir))
        table.add_row("Output Directory", str(settings.output_dir))
        table.add_row("Cache Directory", str(settings.cache_dir))

        console.print(table)

    except Exception as e:
        console.print(f"\n[red]✗ Error:[/red] {e}", style="bold red")
        raise click.Abort()


if __name__ == "__main__":
    cli()
