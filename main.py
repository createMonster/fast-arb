#!/usr/bin/env python3
"""Main entry point for the Funding Rate Arbitrage MVP"""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from loguru import logger

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.arbitrage.arbitrage_engine import ArbitrageEngine, EngineStatus
from src.config.config_manager import ConfigManager
from src.utils.logger import setup_logger


console = Console()


class ArbitrageApp:
    """Main application class"""
    
    def __init__(self, config_path: str, log_level: str = "INFO"):
        self.config_path = config_path
        self.log_level = log_level
        self.engine: Optional[ArbitrageEngine] = None
        self.running = False
        
        # Setup logging
        setup_logger(log_level=log_level)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        console.print("\n[yellow]Received shutdown signal, stopping gracefully...[/yellow]")
        self.running = False
        if self.engine:
            asyncio.create_task(self.engine.stop())
    
    async def run(self, monitor_only: bool = False) -> None:
        """Run the arbitrage application"""
        try:
            # Initialize engine
            console.print("[blue]Initializing Arbitrage Engine...[/blue]")
            self.engine = ArbitrageEngine(self.config_path)
            
            if not await self.engine.initialize():
                console.print("[red]Failed to initialize engine[/red]")
                return
            
            # Start engine
            console.print("[green]Starting Arbitrage Engine...[/green]")
            if not await self.engine.start():
                console.print("[red]Failed to start engine[/red]")
                return
            
            self.running = True
            
            if monitor_only:
                await self._run_monitor_mode()
            else:
                await self._run_trading_mode()
                
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted by user[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.error(f"Application error: {e}")
        finally:
            if self.engine:
                await self.engine.stop()
    
    async def _run_monitor_mode(self) -> None:
        """Run in monitoring mode (no trading)"""
        console.print("[cyan]Running in MONITOR mode (no trading)[/cyan]")
        
        with Live(self._create_monitor_layout(), refresh_per_second=1) as live:
            while self.running and self.engine.get_status() == EngineStatus.RUNNING:
                live.update(self._create_monitor_layout())
                await asyncio.sleep(1)
    
    async def _run_trading_mode(self) -> None:
        """Run in full trading mode"""
        console.print("[green]Running in TRADING mode[/green]")
        
        with Live(self._create_trading_layout(), refresh_per_second=1) as live:
            while self.running and self.engine.get_status() == EngineStatus.RUNNING:
                live.update(self._create_trading_layout())
                await asyncio.sleep(1)
    
    def _create_monitor_layout(self) -> Layout:
        """Create monitor mode layout"""
        layout = Layout()
        
        layout.split_column(
            Layout(self._create_status_panel(), size=8),
            Layout(self._create_spreads_panel(), size=12),
            Layout(self._create_opportunities_panel())
        )
        
        return layout
    
    def _create_trading_layout(self) -> Layout:
        """Create trading mode layout"""
        layout = Layout()
        
        layout.split_column(
            Layout(self._create_status_panel(), size=8),
            Layout().split_row(
                Layout(self._create_spreads_panel()),
                Layout(self._create_executions_panel())
            ),
            Layout(self._create_opportunities_panel(), size=10)
        )
        
        return layout
    
    def _create_status_panel(self) -> Panel:
        """Create status panel"""
        if not self.engine:
            return Panel("Engine not initialized", title="Status")
        
        stats = self.engine.get_statistics()
        status = self.engine.get_status()
        
        status_color = {
            EngineStatus.RUNNING: "green",
            EngineStatus.STOPPED: "red",
            EngineStatus.ERROR: "red",
            EngineStatus.STARTING: "yellow",
            EngineStatus.STOPPING: "yellow"
        }.get(status, "white")
        
        content = f"""
[bold]Status:[/bold] [{status_color}]{status.value.upper()}[/{status_color}]
[bold]Uptime:[/bold] {stats.uptime_seconds:.0f}s
[bold]Opportunities:[/bold] {stats.opportunities_detected} detected, {stats.opportunities_executed} executed
[bold]Success Rate:[/bold] {stats.success_rate:.1%}
[bold]Total PnL:[/bold] ${stats.total_pnl:.2f}
[bold]Active Positions:[/bold] {stats.active_positions}
[bold]Errors:[/bold] {stats.errors_count}
"""
        
        return Panel(content, title="🤖 Engine Status", border_style=status_color)
    
    def _create_spreads_panel(self) -> Panel:
        """Create funding rate spreads panel"""
        if not self.engine:
            return Panel("No data", title="Funding Rate Spreads")
        
        spreads = self.engine.get_current_spreads()
        
        if not spreads:
            return Panel("No spread data available", title="📊 Funding Rate Spreads")
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Symbol", style="cyan")
        table.add_column("Reya Rate", justify="right")
        table.add_column("Hyperliquid Rate", justify="right")
        table.add_column("Spread", justify="right")
        table.add_column("Status", justify="center")
        
        for symbol, spread in spreads.items():
            spread_color = "green" if abs(spread.spread_percentage) > 0.1 else "white"
            status_emoji = "🔥" if abs(spread.spread_percentage) > 0.2 else "📈" if abs(spread.spread_percentage) > 0.1 else "📊"
            
            table.add_row(
                symbol,
                f"{spread.reya_rate:.4f}%",
                f"{spread.hyperliquid_rate:.4f}%",
                f"[{spread_color}]{spread.spread_percentage:+.4f}%[/{spread_color}]",
                status_emoji
            )
        
        return Panel(table, title="📊 Funding Rate Spreads")
    
    def _create_opportunities_panel(self) -> Panel:
        """Create opportunities panel"""
        if not self.engine:
            return Panel("No data", title="Opportunities")
        
        opportunities = self.engine.get_active_opportunities()
        
        if not opportunities:
            return Panel("No active opportunities", title="🎯 Active Opportunities")
        
        table = Table(show_header=True, header_style="bold green")
        table.add_column("Symbol", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Expected Profit", justify="right")
        table.add_column("Risk/Reward", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Status")
        
        for opp in opportunities[-5:]:  # Show last 5
            profit_color = "green" if opp.expected_profit > 0 else "red"
            confidence_color = "green" if opp.confidence > 0.8 else "yellow" if opp.confidence > 0.6 else "red"
            
            table.add_row(
                opp.symbol,
                opp.opportunity_type.value,
                f"[{profit_color}]${opp.expected_profit:.2f}[/{profit_color}]",
                f"{opp.risk_reward_ratio:.2f}",
                f"[{confidence_color}]{opp.confidence:.1%}[/{confidence_color}]",
                opp.status.value
            )
        
        return Panel(table, title="🎯 Active Opportunities")
    
    def _create_executions_panel(self) -> Panel:
        """Create recent executions panel"""
        if not self.engine:
            return Panel("No data", title="Recent Executions")
        
        executions = self.engine.get_recent_executions(5)
        
        if not executions:
            return Panel("No recent executions", title="⚡ Recent Executions")
        
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Symbol", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("PnL", justify="right")
        table.add_column("Status")
        table.add_column("Time")
        
        for exec in executions:
            pnl_color = "green" if exec.realized_pnl > 0 else "red" if exec.realized_pnl < 0 else "white"
            status_color = "green" if exec.status.value == "completed" else "red" if exec.status.value == "failed" else "yellow"
            
            table.add_row(
                exec.symbol,
                f"{exec.executed_size:.4f}",
                f"[{pnl_color}]${exec.realized_pnl:.2f}[/{pnl_color}]",
                f"[{status_color}]{exec.status.value}[/{status_color}]",
                exec.started_at.strftime("%H:%M:%S")
            )
        
        return Panel(table, title="⚡ Recent Executions")


@click.group()
@click.option('--config', '-c', default='config/config.yaml', help='Configuration file path')
@click.option('--log-level', '-l', default='INFO', help='Log level (DEBUG, INFO, WARNING, ERROR)')
@click.pass_context
def cli(ctx, config, log_level):
    """Funding Rate Arbitrage MVP"""
    ctx.ensure_object(dict)
    ctx.obj['config'] = config
    ctx.obj['log_level'] = log_level


@cli.command()
@click.option('--monitor-only', '-m', is_flag=True, help='Run in monitor mode (no trading)')
@click.pass_context
def run(ctx, monitor_only):
    """Run the arbitrage engine"""
    config_path = ctx.obj['config']
    log_level = ctx.obj['log_level']
    
    console.print(Panel.fit(
        "[bold blue]Funding Rate Arbitrage MVP[/bold blue]\n"
        "[yellow]Reya Network ⟷ Hyperliquid[/yellow]",
        border_style="blue"
    ))
    
    if monitor_only:
        console.print("[cyan]Starting in MONITOR mode (no trading will occur)[/cyan]")
    else:
        console.print("[green]Starting in TRADING mode[/green]")
    
    app = ArbitrageApp(config_path, log_level)
    asyncio.run(app.run(monitor_only))


@cli.command()
@click.pass_context
def config_check(ctx):
    """Check configuration file"""
    config_path = ctx.obj['config']
    
    try:
        config_manager = ConfigManager(config_path)
        
        if config_manager.validate_config():
            console.print("[green]✅ Configuration file is valid[/green]")
            
            # Display key settings
            table = Table(title="Configuration Summary")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            
            general_config = config_manager.get_general_config()
            arbitrage_config = config_manager.get_arbitrage_config()
            risk_config = config_manager.get_risk_management_config()
            trading_pairs = config_manager.get_trading_pairs()
            
            table.add_row("Dry Run Mode", str(config_manager.is_dry_run()))
            table.add_row("Log Level", config_manager.get_log_level())
            table.add_row("Update Interval", f"{general_config.update_interval}s")
            table.add_row("Trading Pairs", ", ".join([pair.symbol for pair in trading_pairs]))
            table.add_row("Min Spread Threshold", f"{arbitrage_config.funding_rate.get('min_spread_threshold', 0.5)}%")
            table.add_row("Max Position Size", f"${risk_config.max_total_position}")
        else:
            console.print("[red]❌ Configuration validation failed[/red]")
            sys.exit(1)
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]❌ Configuration error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.pass_context
def test_connections(ctx):
    """Test exchange connections"""
    config_path = ctx.obj['config']
    log_level = ctx.obj['log_level']
    
    async def test():
        try:
            setup_logger(log_level=log_level)
            
            console.print("[blue]Testing exchange connections...[/blue]")
            
            engine = ArbitrageEngine(config_path)
            
            if await engine.initialize():
                console.print("[green]✅ All connections successful[/green]")
                await engine.stop()
            else:
                console.print("[red]❌ Connection test failed[/red]")
                sys.exit(1)
                
        except Exception as e:
            console.print(f"[red]❌ Connection test error: {e}[/red]")
            sys.exit(1)
    
    asyncio.run(test())


@cli.command()
@click.option('--symbol', '-s', help='Specific symbol to check')
@click.pass_context
def check_spreads(ctx, symbol):
    """Check current funding rate spreads"""
    config_path = ctx.obj['config']
    log_level = ctx.obj['log_level']
    
    async def check():
        try:
            setup_logger(log_level="WARNING")  # Reduce log noise
            
            console.print("[blue]Checking current funding rate spreads...[/blue]")
            
            engine = ArbitrageEngine(config_path)
            
            if not await engine.initialize():
                console.print("[red]❌ Failed to initialize[/red]")
                return
            
            if not await engine.start():
                console.print("[red]❌ Failed to start[/red]")
                return
            
            # Wait for initial data
            await asyncio.sleep(5)
            
            spreads = engine.get_current_spreads()
            
            if symbol:
                spreads = {k: v for k, v in spreads.items() if k == symbol}
            
            if not spreads:
                console.print("[yellow]No spread data available[/yellow]")
            else:
                table = Table(title="Current Funding Rate Spreads")
                table.add_column("Symbol", style="cyan")
                table.add_column("Reya Rate", justify="right")
                table.add_column("Hyperliquid Rate", justify="right")
                table.add_column("Spread", justify="right")
                table.add_column("Opportunity", justify="center")
                
                for sym, spread in spreads.items():
                    spread_color = "green" if abs(spread.spread_percentage) > 0.1 else "white"
                    opportunity = "🔥" if abs(spread.spread_percentage) > 0.2 else "📈" if abs(spread.spread_percentage) > 0.1 else "📊"
                    
                    table.add_row(
                        sym,
                        f"{spread.reya_rate:.4f}%",
                        f"{spread.hyperliquid_rate:.4f}%",
                        f"[{spread_color}]{spread.spread_percentage:+.4f}%[/{spread_color}]",
                        opportunity
                    )
                
                console.print(table)
            
            await engine.stop()
            
        except Exception as e:
            console.print(f"[red]❌ Error checking spreads: {e}[/red]")
    
    asyncio.run(check())


if __name__ == "__main__":
    cli()