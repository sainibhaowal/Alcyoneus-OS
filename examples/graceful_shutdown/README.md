# Graceful Shutdown Example

This example demonstrates how to implement graceful shutdown in a long-running Alcyoneus OS application with proper signal handling.

## Features Demonstrated

1. **Signal Handling**: Responds to SIGTERM and SIGINT (Ctrl+C)
2. **Protected Sections**: Critical initialization and cleanup protected from interruption
3. **Shutdown Statistics**: Detailed logging of resource cleanup
4. **Long-Running Service**: Simulates a service that processes tasks continuously
5. **Proper Resource Management**: Ensures all resources are cleaned up on shutdown

## Running the Example

```bash
# Activate your environment
source .venv/bin/activate

# Run the example
python examples/graceful_shutdown/graceful_shutdown_example.py
```

## What to Expect

When you run the example:

1. **Initialization**: The application initializes (protected from interruption)
2. **Main Loop**: Starts processing tasks continuously
3. **Graceful Shutdown**: Press Ctrl+C at any time to trigger graceful shutdown
4. **Cleanup**: All resources are cleaned up properly
5. **Statistics**: Detailed shutdown statistics are logged

Example output:
```
2025-10-15 23:00:00,000 - __main__ - INFO - === Graceful Shutdown Example ===
2025-10-15 23:00:00,001 - __main__ - INFO - Building and compiling graph...
2025-10-15 23:00:00,100 - __main__ - INFO - Signal handlers registered (Ctrl+C to stop)
2025-10-15 23:00:00,101 - __main__ - INFO - Starting initialization (protected from interruption)...
2025-10-15 23:00:02,102 - __main__ - INFO - Initialization complete
2025-10-15 23:00:02,103 - __main__ - INFO - Entering main loop. Press Ctrl+C to shutdown gracefully...
2025-10-15 23:00:02,104 - __main__ - INFO - Processing task #1
2025-10-15 23:00:03,105 - __main__ - INFO - Task #1 completed: {...}
^C
2025-10-15 23:00:04,106 - __main__ - INFO - Received KeyboardInterrupt (Ctrl+C)
2025-10-15 23:00:04,107 - __main__ - INFO - Starting cleanup (protected from interruption)...
2025-10-15 23:00:04,200 - __main__ - INFO - === Shutdown Statistics ===
2025-10-15 23:00:04,201 - __main__ - INFO - Total duration: 0.10s
2025-10-15 23:00:04,201 - __main__ - INFO - Background tasks: {'status': 'completed', ...}
2025-10-15 23:00:04,201 - __main__ - INFO - Cleanup complete
2025-10-15 23:00:04,202 - __main__ - INFO - Processed 1 tasks total
2025-10-15 23:00:04,202 - __main__ - INFO - Application shutdown complete
```

## Key Concepts

### 1. Shutdown Manager

```python
shutdown_manager = GracefulShutdownManager(shutdown_timeout=30.0)
shutdown_manager.register_signal_handlers()
```

The `GracefulShutdownManager` handles SIGTERM and SIGINT signals gracefully.

### 2. Protected Sections

```python
with shutdown_manager.protect_section():
    await initialize_resources()
```

Critical sections (initialization, cleanup) are protected from interruption.

### 3. Shutdown Loop

```python
while not shutdown_manager.shutdown_requested:
    await process_task()
```

Check the shutdown flag regularly to exit gracefully.

### 4. Proper Cleanup

```python
finally:
    with shutdown_manager.protect_section():
        stats = await graph.aclose()
        shutdown_manager.unregister_signal_handlers()
```

Cleanup is always performed and protected from interruption.

## Testing Shutdown Behavior

Try these scenarios:

1. **Normal Shutdown**: Press Ctrl+C during task processing
2. **During Initialization**: Try Ctrl+C during the 2-second initialization (it will be delayed)
3. **Multiple Signals**: Press Ctrl+C multiple times rapidly (only first is processed)
4. **Quick Shutdown**: Press Ctrl+C immediately after start

## Customization

You can customize the shutdown behavior:

```python
# Adjust shutdown timeout
shutdown_manager = GracefulShutdownManager(shutdown_timeout=60.0)
graph.compile(shutdown_timeout=60.0)

# Add custom shutdown callbacks
def on_shutdown():
    logger.info("Custom cleanup logic")

shutdown_manager.add_shutdown_callback(on_shutdown)
```

## Learn More

- [Graceful Shutdown Guide](../../docs/Concept/graceful-shutdown.md)
- [Async Patterns Guide](../../docs/Concept/async-patterns.md)
- [CompiledGraph API Reference](../../docs/reference/)
