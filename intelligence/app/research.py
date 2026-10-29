"""
The loop the scheduled agents share (the pregame brief, the data-check
investigator): research with tools for a few rounds, write, check the
draft in code, and allow one rewrite with the problems listed.
Unlike the chat agent there's no streaming and no one reading along, so a
draft that still fails comes back as text None for the caller to fall back.
"""

import asyncio
from dataclasses import dataclass, field

from .providers import ProviderChain, echo_tool_call


@dataclass
class Draft:
    text: str | None  # None: no draft passed the checks
    model: str | None
    problems: list[str] = field(default_factory=list)  # why the last draft failed, if it did
    tools: list[str] = field(default_factory=list)  # what the agent looked up


async def research_and_write(chain: ProviderChain, runner, instructions: str, prompt: str, tools: list[dict],
                             check, rounds: int, max_tokens: int, finish: str) -> Draft:
    """
    runner.run(name, arguments) -> JSON text runs each tool call; check(text,
    sources) -> problems. The sources a draft is checked against are the
    prompt and every tool result (not the instructions). Raises
    AllProvidersFailed if no provider answers.
    """
    messages = [{"role": "system", "content": instructions}, {"role": "user", "content": prompt}]
    results, used, start = [], [], 0
    for round_number in range(rounds + 1):
        last = round_number == rounds
        if last:
            messages.append({"role": "user", "content": finish})
        message, provider, start = await chain.complete_with_tools(messages, None if last else tools, max_tokens, start=start)
        calls = [] if last else list(message.tool_calls or [])
        if not calls:
            break
        messages.append({"role": "assistant", "content": message.content, "tool_calls": [echo_tool_call(c) for c in calls]})
        outputs = await asyncio.gather(*(runner.run(c.function.name, c.function.arguments) for c in calls))
        for call, output in zip(calls, outputs):
            messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
            results.append(output)
            used.append(f"{call.function.name}({call.function.arguments})")

    sources = "\n".join([prompt, *results])
    text = (message.content or "").strip()
    problems = check(text, sources)
    if problems:
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Fix these problems and reply with only the corrected text:\n- "
                      + "\n- ".join(problems)}]
        message, provider, _ = await chain.complete_with_tools(messages, None, max_tokens, start=start)
        text = (message.content or "").strip()
        problems = check(text, sources)
    if problems:
        return Draft(None, provider.label, problems, used)
    return Draft(text, provider.label, [], used)
