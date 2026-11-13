"""
AI.py - the learning engine for ForgetMeNot. No GUI code lives here.

Idea: take a small pretrained language model (it already understands English), teach it
FICTIONAL facts in sequential lessons, and after every lesson measure how confident it is in
EVERY fact it has been taught. Because the facts are invented, the model cannot already know
them, so any confidence it shows came from our training, and any drop is forgetting.

Install:  pip install torch transformers peft
"""

import csv
import math
import random
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ---------------------------------------------------------------- settings you can tweak
MODELS = {  # name shown in the GUI -> (Hugging Face id, LoRA target layers)
    "SmolLM": ("HuggingFaceTB/SmolLM2-135M", ["q_proj", "v_proj"]),
    "GPT-2": ("gpt2", ["c_attn"]),
    "Qwen2.5-0.5B": ("Qwen/Qwen2.5-0.5B", ["q_proj", "v_proj"]),
}
METHODS = ["Plain", "LoRA", "Replay", "EWC"]
METHOD_TIPS = {
    "Plain": "Full fine-tuning on each new lesson only. Expect the most forgetting.",
    "LoRA": "Trains small adapter layers only. Usually needs a HIGHER learning rate (try 0.001).",
    "Replay": "Mixes a sample of old facts into each new lesson.",
    "EWC": "Penalizes changes to weights that mattered for earlier lessons.",
}
N_LESSONS = 5
FACTS_PER_LESSON = 4
REPLAY_FRACTION = 0.25   # Replay: re-teach this fraction of old facts each lesson
EWC_LAMBDA = 100.0       # EWC: penalty strength (raise it to protect old facts harder)
BATCH_SIZE = 8
RESULTS_FILE = Path(__file__).resolve().parent / "results" / "results.csv"
LINKS_FILE = Path(__file__).resolve().parent / "results" / "links.csv"


# ---------------------------------------------------------------- fictional facts
SYLLABLES = ["zor", "vath", "el", "mar", "kar", "row", "lin", "tav", "ora", "quil",
             "dren", "sho", "bel", "nym", "ith", "gar", "pel", "uun", "fey", "tosk"]

# (topic, three phrasings of the question, answer pattern). {b} = subject, {a} = the answer name
TEMPLATES = [
    ("Geography", ["What is the capital of {b}?", "Which city is the capital of {b}?",
                   "{b}'s capital city is called what?"], "{a}"),
    ("Inventions", ["Who invented the {b}?", "Which person created the {b}?",
                    "The {b} was invented by whom?"], "{a}"),
    ("Nature", ["Which sea does the {b} River flow into?", "The {b} River empties into which sea?",
                "Into what sea does the {b} River run?"], "the {a} Sea"),
    ("People", ["Where was {b} born?", "In which town was {b} born?",
                "{b} is originally from which town?"], "{a}"),
]


# Which templates build on an earlier fact in the same lesson
# Maps the template index of the dependent fact to the template index of the fact it needs
# Geography (0) gives a city that Nature (2) uses as a river name and Inventions (1) gives a person that People (3) asks about
CHAINS = {2: 0, 3: 1}


# Builds the invented facts and the links between them, the same seed always gives the same facts
# Takes
#    seed the random seed
# Returns
#    facts a list of fact dictionaries
#    links a list of (fact id it needs, fact id that needs it) pairs
def make_curriculum(seed):
    rng = random.Random(seed)
    used = set()

    def new_name():
        while True:
            name = "".join(rng.choice(SYLLABLES) for _ in range(rng.choice([2, 3]))).capitalize()
            if name not in used:
                used.add(name)
                return name

    facts = []
    links = []
    for i in range(N_LESSONS * FACTS_PER_LESSON):
        t = i % len(TEMPLATES)
        topic, questions, answer = TEMPLATES[t]
        a = new_name()
        if t in CHAINS:
            parent = facts[i - (t - CHAINS[t])]
            b = parent["answer_name"]
            links.append((parent["id"], i))
        else:
            b = new_name()
        facts.append({
            "id": i, "lesson": i // FACTS_PER_LESSON + 1, "topic": topic, "subject": b,
            "questions": [q.format(a=a, b=b) for q in questions],
            "answer": answer.format(a=a, b=b), "answer_name": a,
        })
    return facts, links



def withContext(factB, factA):
    statement = factA["questions"][0] + " " + factA["answer"]
    copy = dict(factB)
    copy["questions"] = [statement + " " + q for q in factB["questions"]]
    return copy


# ---------------------------------------------------------------- the experiment
class Experiment:
    """One experiment = one model + one method + one seed, taught lesson by lesson."""

    def __init__(self, model_name, method, seed):
        self.model_name, self.method, self.seed = model_name, method, seed
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        torch.manual_seed(seed)
        self.rng = random.Random(seed)

        hf_id, lora_targets = MODELS[model_name]
        self.tok = AutoTokenizer.from_pretrained(hf_id)
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(hf_id)
        if method == "LoRA":
            from peft import LoraConfig, get_peft_model  # only needed for LoRA
            cfg = LoraConfig(r=8, lora_alpha=16, target_modules=lora_targets,
                             lora_dropout=0.0, task_type="CAUSAL_LM")
            self.model = get_peft_model(self.model, cfg)
        self.model.to(self.device)

        self.facts, self.links = make_curriculum(seed)
        self.lesson = 0
        self.taught = []                 # facts taught so far
        self.fisher = self.anchor = None  # EWC memory
        self.run_id = time.strftime("%Y%m%d-%H%M%S")
        self.progress = print            # the GUI replaces this to show messages in its log

    # ------------------------------------------------------------ text -> tensors
    def _encode(self, question, answer, eos):
        """Prompt + answer as token ids; labels only cover the answer (prompt masked with -100)."""
        prompt = self.tok(f"Question: {question}\nAnswer:", add_special_tokens=False).input_ids
        ans = self.tok(" " + answer, add_special_tokens=False).input_ids
        if eos:
            ans = ans + [self.tok.eos_token_id]
        return prompt + ans, [-100] * len(prompt) + ans

    def _batch(self, encoded):
        n = max(len(ids) for ids, _ in encoded)
        pad = self.tok.pad_token_id
        ids = torch.tensor([i + [pad] * (n - len(i)) for i, _ in encoded])
        labels = torch.tensor([l + [-100] * (n - len(l)) for _, l in encoded])
        mask = torch.tensor([[1] * len(i) + [0] * (n - len(i)) for i, _ in encoded])
        return ids.to(self.device), mask.to(self.device), labels.to(self.device)

    # ------------------------------------------------------------ measuring memory
    @torch.no_grad()
    def confidences(self, facts):
        """fact id -> confidence in [0, 1].

        Confidence = the model's average per-token probability of the CORRECT answer, averaged
        over three phrasings of the question (the model only trains on two of them).
        """
        self.model.eval()
        items = [(f["id"], self._encode(q, f["answer"], eos=False))
                 for f in facts for q in f["questions"]]
        scores = {}
        for start in range(0, len(items), 16):
            chunk = items[start:start + 16]
            ids, mask, labels = self._batch([enc for _, enc in chunk])
            logits = self.model(input_ids=ids, attention_mask=mask).logits
            loss = torch.nn.functional.cross_entropy(
                logits[:, :-1].transpose(1, 2), labels[:, 1:], ignore_index=-100, reduction="none")
            per_token = loss.sum(1) / (labels[:, 1:] != -100).sum(1)
            for (fid, _), value in zip(chunk, per_token.tolist()):
                scores.setdefault(fid, []).append(math.exp(-value))
        return {fid: sum(v) / len(v) for fid, v in scores.items()}

    # ------------------------------------------------------------ training
    def _train(self, pairs, lr, epochs):
        params = [p for p in self.model.parameters() if p.requires_grad]
        optimizer = torch.optim.AdamW(params, lr=lr, weight_decay=0.0)
        pairs = list(pairs)
        self.model.train()
        loss_value = 0.0
        started = time.time()
        for epoch in range(epochs):
            self.rng.shuffle(pairs)
            for s in range(0, len(pairs), BATCH_SIZE):
                ids, mask, labels = self._batch(pairs[s:s + BATCH_SIZE])
                loss = self.model(input_ids=ids, attention_mask=mask, labels=labels).loss
                if self.method == "EWC" and self.fisher is not None:
                    loss = loss + self._ewc_penalty()
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                loss_value = loss.item()
            self.progress(f"  epoch {epoch + 1}/{epochs}  loss {loss_value:.3f}  ({time.time() - started:.0f}s)")
        self.model.eval()
        return loss_value

    def _ewc_penalty(self):
        total = torch.zeros((), device=self.device)
        for name, p in self.model.named_parameters():
            if name in self.fisher:
                total = total + (self.fisher[name] * (p - self.anchor[name]) ** 2).sum()
        return EWC_LAMBDA / 2 * total

    def _consolidate(self, pairs):
        """EWC: record which weights mattered for these examples (squared gradients)."""
        fisher = {n: torch.zeros_like(p) for n, p in self.model.named_parameters() if p.requires_grad}
        self.model.eval()
        for enc in pairs:
            ids, mask, labels = self._batch([enc])
            self.model.zero_grad()
            self.model(input_ids=ids, attention_mask=mask, labels=labels).loss.backward()
            for n, p in self.model.named_parameters():
                if p.grad is not None and n in fisher:
                    fisher[n] += p.grad.detach() ** 2
        self.model.zero_grad()
        top = max(f.max() for f in fisher.values()).item()
        if top > 0:
            fisher = {n: f / top for n, f in fisher.items()}   # scale so the largest value is 1
        if self.fisher is not None:
            fisher = {n: fisher[n] + self.fisher[n] for n in fisher}
        self.fisher = fisher
        self.anchor = {n: p.detach().clone() for n, p in self.model.named_parameters() if n in fisher}

    # ------------------------------------------------------------ one lesson
    def teach_next_lesson(self, lr, epochs):
        if self.lesson >= N_LESSONS:
            raise ValueError("All lessons are done. Press Restart Training to start a new experiment.")
        self.lesson += 1
        new = [f for f in self.facts if f["lesson"] == self.lesson]
        old = list(self.taught)
        self.progress("Scoring facts before training...")
        old_before = self.confidences(old) if old else {}
        new_before = self.confidences(new)      # should be ~0: the model can't know invented facts

        def pairs_for(facts):  # train on the first two phrasings only
            return [self._encode(q, f["answer"], eos=True) for f in facts for q in f["questions"][:2]]

        new_pairs = pairs_for(new)
        train_pairs = list(new_pairs)
        if self.method == "Replay" and old:
            k = max(1, round(REPLAY_FRACTION * len(old)))
            train_pairs += pairs_for(self.rng.sample(old, k))
        self.progress(f"Training on {len(train_pairs)} examples...")
        loss = self._train(train_pairs, lr, epochs)
        if self.method == "EWC":
            self._consolidate(new_pairs)

        self.taught = old + new
        self.progress("Scoring all facts after training...")
        after = self.confidences(self.taught)
        rows = [{
            "run_id": self.run_id, "model": self.model_name, "method": self.method,
            "seed": self.seed, "learning_rate": lr, "epochs": epochs, "lesson": self.lesson,
            "fact_id": f["id"], "topic": f["topic"], "subject": f["subject"],
            "learned_in_lesson": f["lesson"], "confidence": round(after[f["id"]], 4),
        } for f in self.taught]
        self._save(rows)

        self.progress("Testing connections between facts")
        links = self.linkRows(self.links)
        self._save(links, LINKS_FILE)

        def mean(d, facts):
            return sum(d[f["id"]] for f in facts) / len(facts) if facts else None
        return {
            "lesson": self.lesson, "loss": loss, "facts": rows, "links": links,
            "new_before": mean(new_before, new), "new_after": mean(after, new),
            "old_before": mean(old_before, old), "old_after": mean(after, old),
        }

    # Appends rows to a csv file and if Excel has it locked saves to a backup file instead
    # Takes
    #    rows a list of dictionaries that all have the same keys
    #    file the csv file to append to and results.csv is used when none is given
    def _save(self, rows, file=None):
        if not rows:
            return
        file = file or RESULTS_FILE
        file.parent.mkdir(exist_ok=True)
        backup = file.with_name(f"{file.stem}_{self.run_id}.csv")
        for path in (file, backup):
            try:
                is_new = not path.exists()
                with open(path, "a", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                    if is_new:
                        writer.writeheader()
                    writer.writerows(rows)
                if path == backup:
                    self.progress(f"WARNING: {file.name} is locked (open in Excel?). Saved to {path.name} instead.")
                return
            except PermissionError:
                continue
        self.progress(f"WARNING: could not save {file.name} anywhere. Close the CSV in Excel before running.")


    def linkTest(self, factA, factB):
        plain = self.confidences([factB])[factB["id"]]
        withA = self.confidences([withContext(factB, factA)])[factB["id"]]

        if withA < 0.01:
            dependency = 0
        else:
            dependency = max(0, min(1, (withA - plain) / withA))

        return plain, withA, dependency

    def linkRows(self, links):
        taughtById = {f["id"]: f for f in self.taught}
        rows = []
        for aId, bId in links:
            if aId in taughtById and bId in taughtById:
                plain, withA, dependency = self.linkTest(taughtById[aId], taughtById[bId])
                rows.append({
                    "run_id": self.run_id, "lesson": self.lesson, "from_fact": aId, "to_fact": bId,
                    "plain": round(plain, 4), "with_a": round(withA, 4), "dependency": round(dependency, 4),
                })
        return rows