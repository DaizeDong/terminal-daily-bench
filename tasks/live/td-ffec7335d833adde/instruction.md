# fix: explain HyperEVM HyperCore read failures and unlist two wrongly blacklisted vaults

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## Why

`vault-scanner-looped` was stuck on HyperEVM (chain id 999), looping over the same
blocks and rotating providers without finishing the chain:

```
Switched RPC providers edge.goldsky.com -> hyperliquid-mainnet.g.alchemy.com,
cause: Last exception: Multicall failed for chain 999
Block 44,367,203, batch size: 40: {'code': -32003, 'message': 'out of gas: gas required exceeds: [redacted-sha]'}
...
Block 44,320,403, batch size: 13: {'code': -32003, 'message': 'out of gas: gas required exceeds: [redacted-sha]'}
```

The reduced batches printed 11 and then 3 addresses, which is not enough to name the
culprit from the log. The initial plan was to blacklist whatever address was
responsible; investigation showed that would have been wrong.

### Isolating the address

The failing payloads are Multicall3 `tryBlockAndAggregate(false, calls)`
(`0x399542e9`) blobs, so they can be replayed verbatim, group by group, against each
configured provider at the failing blocks:

| Batch replayed at block 44,367,203 | goldsky | dRPC | Alchemy |
|------------------------------------|---------|------|---------|
| full 40-call batch | out of gas | out of gas | ok |
| full 40-call batch minus `0x4d0fF6a0…` | ok | ok | ok |
| 13-call reduced batch | out of gas | out of gas | ok |
| `0x4d0fF6a0…` 4 calls duplicated ×2 | out of gas | out of gas | ok |
| every other address, calls duplicated ×16 | ok | ok | ok |

Group bisection of the 13-call batch (`A` = `0x4aBFd796…`, `S` = `0x4d0fF6a0…`,
`B` = `0x7188D14A…`): `A` ok, `S` ok, `B` ok, `A+S` ok, `A+B` ok, `S+B` fails, and
`S` alone duplicated fails. One address accounts for the entire failure:
**`0x4d0fF6a0DD9f7316b674Fb37993A3Ce28BEA340e`, Hyperdrive Liquid Staked Hype
(`HYPED`)**. Only three of its selectors misbehave, and `totalSupply()` never does.

### Hypothesis confirmed from the smart contract source

The hypothesis was a HyperCore read dependency. The vault is an ERC-1967 proxy whose
implementation `0x6CA870794cd307243FCc8711899e46C74B2D3f2f` **is** source-verified
(Etherscan v2 unified API with `chainid=999`) as `StakingVaultUpgradeable`, solc
0.8.28 — contrary to the "Hyperdrive contracts are unverified" note we carried. Reading
it confirms the hypothesis exactly.

`StakingVaultUpgradeable.totalAssets()` delegates to `CoreControllerLib`:

```solidity
function totalAssets(StakingVaultUpgradeable.StakingStorage storage $) public view returns (uint256 total) {
  address[] memory proxies = $.proxies.values();
  uint256 blockNumber = compositeBlockNumber();
  for (uint256 i = 0; i < proxies.length; i++) {
    total += totalAssets($, proxies[i], blockNumber);
  }
  total += address(this).balance - $.totalClaimableAssets;
}
```

Every per-proxy step reads live HyperCore state, and the block number itself is a
HyperCore read:

```solidity
total += Wei.wrap(CoreReaderLib.readSpotBalance(proxy, $.tokenIndex).total).fromWei();
CoreReaderLib.DelegatorSummary memory delegatorSummary = CoreReaderLib.readDelegatorSummary(proxy);
...
function compositeBlockNumber() private view returns (uint256) {
  return (uint256(CoreReaderLib.readL1BlockNumber()) << 128) | uint128(block.number);
}
```

`CoreReaderLib` (`@ambitlabs/hypercore`) staticcalls the HyperCore read precompiles
`0x…0801` (spot balance), `0x…0805` (delegator summary) and `0x…0809` (L1 block
number). `getProxies()` returns 3 staking proxies, so one `totalAssets()` performs
**1 + 2 × 3 = 7 HyperCore precompile reads**. `maxDeposit()` calls `totalAssets()`
directly, `convertToAssets()` reaches it through `ERC7535Upgradable`, and
`totalSupply()` is plain ERC-20 storage:

| Selector | Method | Behaviour |
|----------|--------|-----------|
| `0x01e1d114` | `totalAssets()` | heavy / reverts historically |
| `0x07a2d13a` | `convertToAssets(uint256)` | heavy / reverts historically |
| `0x402d267d` | `maxDeposit(address)` | heavy / reverts historically |
| `0x18160ddd` | `totalSupply()` | always cheap, always works |

That is exactly the observed pattern.

### Evidence 1 — the historical revert is a HyperCore read failure

The historical revert data is `0x18c34104`, which is
`keccak("ReadFailure(address)")[:4]` — the custom error `CoreReaderLib` raises when a
precompile staticcall fails. Its decoded argument is `0x…0809`, the L1 block-number
precompile, i.e. the first HyperCore read in `totalAssets()`. Availability is a
per-node, per-moment property, not a property of the block:

```
hyperliquid-mainnet.g.alchemy.com  head      -> ok, 2616.51 HYPE
hyperliquid-mainnet.g.alchemy.com  head-200  -> ReadFailure(0x…0809)
edge.goldsky.com                   head      -> ReadFailure(0x…0809)
edge.goldsky.com                   head-200  -> ok, 2616.51 HYPE
lb.drpc.org                        head      -> ReadFailure(0x…0809)
```

A binary search on Alchemy put the boundary at one block: reverting up to 44,372,819,
succeeding from 44,372,820 — about two minutes behind the head. So this vault's NAV
cannot be reconstructed for an arbitrary past block on any provider.

This also explains the `0x18c34104` reverts already recorded in `risk.py` for
Hyperdrive HLP and Gamma Symphony, where we knew the symptom but not the cause.

### Evidence 2 — the gas number is provider accounting, not real execution

Real execution is cheap: binary searching the `gas` field of a direct `eth_call` on
Alchemy, at a block where the HyperCore read succeeds, gives **~117,000 gas** for the
whole `totalAssets()` — roughly 17k per HyperCore read.

The numbers the scanner trips over come from provider-side accounting for those
staticcalls:

| Provider | Measurement |
|----------|-------------|
| Alchemy | `eth_call` executes in ~117k gas; `estimate_gas` of the same call inside Multicall3 reports 2,843,730 |
| goldsky | 4 copies of `totalAssets()` fit in one multicall under the 300M cap, 5 do not → ≥60M attributed per call |
| dRPC | same as goldsky; `maxDeposit()` is heavy there too |

On goldsky and dRPC the rejection is independent of the cap we send — 1M, 10M, 30M,
100M and 299M all come back as `out of gas: gas required exceeds: <cap>`. The node
decides up front that the batch needs more gas than allowed; nothing actually runs out
of gas. A handful of HyperCore reads is enough to push a normal 40-call batch over a
300M/600M cap, which is why the failure flaps between fallbacks and survives
batch-size reduction until the batch happens to exclude this vault.

### Why the vault stays on our list

- Hyperdrive is a real, DefiLlama-listed HyperEVM protocol and this implementation is
  source-verified.
- The vault is alive at the head: `totalAssets()` 2,616.5 HYPE (about $218k at the
  2026-08-28 HYPE mid of $83.47), `totalSupply()` 2,555.6 HYPED, share price 1.0238
  HYPE per HYPED.
- The failure is a provider-side gas-accounting and HyperCore-state-window artefact.
  Alchemy runs the same batch fine.

Blacklisting would permanently drop a live vault for a transient RPC condition — the
same conclusion the goldsky consensus document reached for its own address list. What
we do accept is that historical NAV for HyperCore-reading vaults is only obtainable
near the head and must not be "repaired" by rescanning.

## Lessons learnt

- `0x18c34104` is `CoreReaderLib.ReadFailure(address)`. When a HyperEVM vault reverts
  with it, the argument names the precompile that could not be read, so the revert
  means "this node cannot serve the HyperCore view for that block" rather than "the
  vault is broken".
- Provider gas accounting for HyperCore precompile reads varies by two orders of
  magnitude (117k real vs ≥60M attributed), so `-32003 out of gas` on chain 999 is not
  evidence of a bad contract, and the same batch may pass on another provider in the
  same fallback mix.
- A `-32003` batch abort can be attributed to a single address by replaying the logged
  `tryBlockAndAggregate` payload group by group, and by duplicating one address's calls
  until the cap is exceeded. Duplication (`×2`, `×4`, `×8`) is what separates a genuine
  gas hog from an innocent bystander that merely shared the batch.
- "Unverified contracts" notes go stale. This implementation is verified on chain 999
  through the Etherscan v2 unified API even though our Hyperdrive metadata says
  otherwise.

## Summary

- Added `docs/README-hyperevm-hypercore-read-gas.md`: symptom, the replay/bisection
  method that isolates the address, the verified-source evidence, the precompile
  table, both measurement tables, the "why we do not blacklist" reasoning and a
  reproduction snippet.
- Cross-linked it from `docs/README-hyperevm-goldsky-failure.md` and added it to the
  README index table in `CLAUDE.md`.
- `eth_defi/erc_4626/vault_protocol/hyperdrive_hl/vault.py`: documented the HyperCore
  read dependency, the two scanner consequences and the corrected verification status.
- `eth_defi/erc_4626/classification.py`: replaced the bare `# Hyperdrive vault`
  comment on the HYPED entry with the reason it is deliberately kept on the list.
- `eth_defi/event_reader/multicall_batcher.py`: line comments on the `"out of gas"`
  retry clue and on the `MulticallRetryable` fallback, warning against blacklisting a
  HyperEVM address that reads HyperCore.
- `eth_defi/vault/risk.py`: explained what `0x18c34104` is in the existing Hyperdrive
  HLP / Gamma Symphony comment and recorded that HYPED is intentionally not listed.
- `tests/vault/test_flag.py`: `test_hypercore_reading_vault_is_not_blacklisted` guards
  the decision.

No behaviour change — documentation, comments and one regression test.

## Related issues and PRs

- Continues the HyperEVM scanner reliability work documented in
  `docs/README-hyperevm-goldsky-failure.md` (eRPC consensus failover to Alchemy).
- Explains the `0x18c34104` revert already referenced by the Hyperdrive HLP and Gamma
  Symphony blacklist entries in `eth_defi/vault/risk.py`.

## Unrelated CI and test fixes

None.

🤖 Generated with [Claude Code]([redacted-url])


---

## Follow-up: blacklist audit of HyperEVM vaults with the same failure mode

Of the 130 addresses in `BROKEN_VAULT_CONTRACTS` + `VAULT_SPECIFIC_RISK`, exactly six
have code on chain 999. `debug_traceCall` with `callTracer` enumerates the precompile
callees of `totalAssets()` even for the unverified ones, and **all six read
HyperCore** — the same dependency as HYPED:

| Vault | Address | Precompiles read by `totalAssets()` | Assets at head | Historical read at head-20,000 (no gas cap) | `estimate_gas` at head | Verdict |
|---|---|---|---|---|---|---|
| LONGV4 | `0x2eEe42A0…` | `0x…0800` position ×2, `0x…0803` withdrawable | 0.00 USDC | Alchemy ok (also head-500k) | 59,501 | **unlisted** |
| Altcopy Flagship | `0xcDB9671E…` | `0x…0801` spot balance, `0x…080f` | 7,765 USDC | ok on all three (also head-500k) | 71,350 | **unlisted** |
| Altcopy Index | `0xF8F7c57F…` | `0x…0801`, `0x…0802` vault equity ×8 | 8,168 USDC | fails everywhere | 222,530 | stays blacklisted |
| Hyperdrive HLP | `0x6ED613E8…` | `0x…0809` L1 block number | 9,025 USDC | `ReadFailure` everywhere | 202,951 | stays blacklisted |
| Gamma Symphony | `0x2b37f356…` | `0x…0809` | 36 USDC | `ReadFailure` everywhere | 144,186 | stays blacklisted |
| HYPE Funding Yield | `0xd3F41DAC…` | `0x…0801` | 10 USD₮0 | reverts everywhere | 126,909 | stays blacklisted |
| HYPED (never listed) | `0x4d0fF6a0…` | `0x…0809` | 2,616 HYPE | `ReadFailure` everywhere | 117,896 | not listed |

Supporting evidence:

- Hyperdrive HLP and Gamma Symphony share the implementation
  `0xa05959fbd41e30396446c36d099e5f3b20fb6ad6`, verified as
  `TokenizedVaultUpgradeable` — the same `CoreReaderLib` consumer as HYPED. The
  `0x18c34104` revert their entries already recorded *is* `CoreReaderLib.ReadFailure`.
- HYPE Funding Yield is unverified, but its runtime bytecode carries
  `SpotBalance precompile call failed`, `MarkPx precompile call failed`,
  `Position precompile call failed` and `Withdrawable precompile call failed`, and
  goldsky answers `execution reverted: SpotBalance precompile…`.
- None of the six is intrinsically expensive — every `estimate_gas` at head is
  59k–223k. The megagas numbers are provider accounting for the precompile
  staticcalls.

### Two entries were wrong

`LONGV4` and `Altcopy Flagship` were blacklisted with "all configured RPC providers
reject the scanner's 2,000,000-gas probes". That 2M figure is the `CALL_GAS` default
of `scripts/erc-4626/poke-hyperevm-vault-calls.py` — a cap the diagnostic script
imposes, not a provider limit. Re-measured without it:

```
LONGV4            Alchemy  head:ok  -20k:ok  -100k:ok  -500k:ok
Altcopy Flagship  Alchemy  head:ok  -20k:ok  -100k:ok  -500k:ok
                  goldsky  head:ok  -20k:ok  -100k:ok  -500k:ok
                  dRPC     head:ok  -20k:ok  -100k:ok  -500k:ok
```

Both were therefore removed from `VAULT_SPECIFIC_RISK` and `BROKEN_VAULT_CONTRACTS`.
Residual risk is accepted and recorded: LONGV4 still draws `-32003` from dRPC and
intermittently from goldsky, so its history will come from the Alchemy pin, and
goldsky rejects Altcopy Flagship's four-probe multicall even though it answers the
same calls individually. LONGV4 is also currently empty (0 USDC), so the activity
filter should keep it out of price scans anyway.

The other four stay blacklisted, but for a corrected reason: not "broken" or
"gas-poisonous", but "historical valuation unobtainable on every provider", which is
what the price pipeline needs. When a head-NAV-only path exists they should be
revisited, since they are live vaults.

### Additional changes in this follow-up

- `scripts/erc-4626/poke-hyperevm-vault-calls.py`: the docstring no longer says
  out-of-gas calls "must be blacklisted"; it warns that `CALL_GAS=[redacted-sha]` is a
  self-imposed cap and prescribes re-measuring without it, at several depths, on
  every provider, plus `debug_traceCall`, before blacklisting.
- `eth_defi/vault/risk.py`: every remaining HyperEVM entry now names the traced
  precompiles, the head assets and the depth measurements.
- `tests/vault/test_flag.py`: `test_healed_hyperevm_vault_is_unblacklisted` asserts
  the two unlisted addresses stay off both lists.
- `docs/README-hyperevm-hypercore-read-gas.md`: new "Blacklist audit" section with
  the table above.

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
