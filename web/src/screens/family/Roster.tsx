import { useState } from "preact/hooks";
import type { JSX } from "preact";
import { Refused } from "../../api/client";
import * as family from "../../api/family";
import type { GrantOut } from "../../api/familyTypes";
import { go } from "../../flow";
import { fromWallInput, namesOf, slotRow, wallTime, weekdayNames } from "../../family/model";
import { t } from "../../strings";
import { Field, Notice, Pill, Tile } from "../../ui/components";
import { FamilyPage, NoticeAt, s, useAct, useHere, useRead, type Here } from "./common";

/** E12-03: the roster (who is on duty, which days, from when to when) and the tasks, each
 *  done only by the person it names — anyone else tapping it is told so by the backend. The
 *  names are the backend's (the family list); the rows are data, never a sentence. Who drives
 *  him to a visit is the Visit screen's suggestion on the chief's yes (#128): one tap there. */
export function RosterPart(): JSX.Element | null {
  const here = useHere();
  const words = s();
  const a = useAct();
  const [noVisit, setNoVisit] = useState(false);
  const pid = here?.papers.profile_id;
  const people = useRead(here ? () => family.grants(here.bearer, here.papers.profile_id, here.lang) : null, [pid, here?.lang]);
  const slots = useRead(here ? () => family.roster(here.bearer, here.papers.profile_id) : null, [pid]);
  const duty = useRead(here ? () => family.onDuty(here.bearer, here.papers.profile_id) : null, [pid]);
  const jobs = useRead(
    here
      ? async () => {
          try {
            return await family.tasks(here.bearer, here.papers.profile_id, false);
          } catch (failure) {
            // Every task is the owner's and his chief's to read; the ones that name you, anyone's.
            if (failure instanceof Refused && failure.status === 403) return family.tasks(here.bearer, here.papers.profile_id, true);
            throw failure;
          }
        }
      : null,
    [pid],
  );
  if (!here) return null;
  const names = namesOf(people.value ?? []);
  if (here.papers.standing === "owner") names.set(here.papers.key_id ?? "", here.papers.display_name);
  const nameOf = (personId: string) => names.get(personId) ?? "";
  const reload = async () => {
    await Promise.all([slots.reload(), duty.reload(), jobs.reload()]);
  };
  const nextVisit = () =>
    a.act("visit", async () => {
      const [first] = await family.appointments(here.bearer, here.papers.profile_id);
      if (first) go({ name: "visit", appointmentId: first.appointment_id });
      else setNoVisit(true);
    });
  return (
    <FamilyPage title={words.roster} part="roster">
      <Tile paper testId="roster">
        <h2 class="title">{words.rosterTitle}</h2>
        {slots.value && slots.value.length > 0 && (
          <table class="data" data-testid="roster-table">
            <thead>
              <tr>
                <th>{words.who}</th>
                <th>{words.days}</th>
                <th>{words.from}</th>
                <th>{words.to}</th>
              </tr>
            </thead>
            <tbody>
              {slots.value.map((slot) => {
                const row = slotRow(slot, names, here.locale);
                return (
                  <tr key={row.slotId} data-testid="roster-row">
                    <td>{row.who}</td>
                    <td>{row.days}</td>
                    <td>{row.from}</td>
                    <td>{row.to}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {duty.value && duty.value.length > 0 && (
          <p class="label" data-testid="on-duty">
            {words.onDutyNow}: {duty.value.map((each) => nameOf(each.person_id)).filter(Boolean).join(", ")}
          </p>
        )}
        {slots.value?.map((slot) => (
          <Pill key={slot.slot_id} quiet onClick={() => void a.act(slot.slot_id, async () => (await family.endSlot(here.bearer, here.papers.profile_id, slot.slot_id), await reload()))} testId="take-off">
            {words.takeOff}: {nameOf(slot.person_id)} {slotRow(slot, names, here.locale).days}
          </Pill>
        ))}
        <Notice error={slots.error} />
        {slots.value?.map((slot) => (
          <NoticeAt key={slot.slot_id} act={a} where={slot.slot_id} />
        ))}
      </Tile>
      {people.value && <NewSlot here={here} people={people.value} act={a} reload={reload} />}
      <Tile paper testId="tasks">
        <h2 class="title">{words.tasksTitle}</h2>
        {jobs.value?.map((task) => (
          <div key={task.task_id} class="entry" data-testid="task">
            <p>{task.what}</p>
            <p class="label">
              {nameOf(task.assigned_person_id)}
              {task.due_at ? ` · ${wallTime(task.due_at, here.locale)}` : ""}
            </p>
            {task.done_at ? (
              <span class="chip" data-testid="task-done">
                {words.doneChip}
              </span>
            ) : (
              <Pill
                onClick={() =>
                  void a.act(task.task_id, async () => {
                    const yes = await family.mintTaskDone(here.bearer, here.papers.profile_id, task.task_id);
                    await family.taskDone(here.bearer, here.papers.profile_id, task.task_id, yes.confirmation_id);
                    await jobs.reload();
                  })
                }
                disabled={a.busy}
                testId="task-done-button"
              >
                {words.done}
              </Pill>
            )}
            <NoticeAt act={a} where={task.task_id} />
          </div>
        ))}
        <Notice error={jobs.error} />
      </Tile>
      {people.value && <NewTask here={here} people={people.value} act={a} reload={jobs.reload} />}
      <Pill onClick={() => void nextVisit()} testId="next-visit">
        {words.nextVisit}
      </Pill>
      {noVisit && (
        <Tile paper testId="no-visit">
          <p>{t().visit.none}</p>
        </Tile>
      )}
      <NoticeAt act={a} where="visit" />
    </FamilyPage>
  );
}

type Act = ReturnType<typeof useAct>;

function PersonChoices({ people, chosen, onChoose, testId }: { people: GrantOut[]; chosen: string | null; onChoose: (grant: GrantOut) => void; testId: string }): JSX.Element {
  return (
    <div class="choices" role="group" aria-label={s().who} data-testid={testId}>
      {people.map((grant) => (
        <Pill key={grant.key_id} chosen={chosen === grant.holder_person_id} onClick={() => onChoose(grant)} testId={`${testId}-${grant.holder_name}`}>
          {grant.holder_name}
        </Pill>
      ))}
    </div>
  );
}

function NewSlot({ here, people, act, reload }: { here: Here; people: GrantOut[]; act: Act; reload: () => Promise<void> }): JSX.Element {
  const words = s();
  const [who, setWho] = useState<GrantOut | null>(null);
  const [days, setDays] = useState<number[]>([]);
  const [from, setFrom] = useState("07:00");
  const [to, setTo] = useState("22:00");
  const names = weekdayNames(here.locale);
  const add = () =>
    act.act("slot", async () => {
      if (!who) return;
      await family.addSlot(here.bearer, here.papers.profile_id, { person_id: who.holder_person_id, role: who.role, weekdays: days, from_time: `${from}:00`, to_time: `${to}:00` });
      setWho(null);
      setDays([]);
      await reload();
    });
  return (
    <Tile paper testId="new-slot">
      <h2 class="title">{words.addSlot}</h2>
      <p class="label">{words.who}</p>
      <PersonChoices people={people} chosen={who?.holder_person_id ?? null} onChoose={setWho} testId="slot-who" />
      <p class="label">{words.days}</p>
      <div class="choices days" role="group" aria-label={words.days} data-testid="slot-days">
        {names.map((name, day) => (
          <Pill key={day} chosen={days.includes(day)} onClick={() => setDays(days.includes(day) ? days.filter((each) => each !== day) : [...days, day].sort())} testId={`slot-day-${day}`}>
            {name}
          </Pill>
        ))}
      </div>
      <div class="row">
        <Field name="slot-from" label={words.from} value={from} onInput={setFrom} type="time" />
        <Field name="slot-to" label={words.to} value={to} onInput={setTo} type="time" />
      </div>
      <Pill plum onClick={() => void add()} disabled={act.busy || !who} testId="add-slot">
        {words.addSlot}
      </Pill>
      <NoticeAt act={act} where="slot" />
    </Tile>
  );
}

function NewTask({ here, people, act, reload }: { here: Here; people: GrantOut[]; act: Act; reload: () => Promise<void> }): JSX.Element {
  const words = s();
  const [what, setWhat] = useState("");
  const [who, setWho] = useState<GrantOut | null>(null);
  const [due, setDue] = useState("");
  const add = () =>
    act.act("task", async () => {
      if (!who) return;
      await family.addTask(here.bearer, here.papers.profile_id, { what: what.trim(), assigned_person_id: who.holder_person_id, due_at: due ? fromWallInput(due) : null });
      setWhat("");
      setWho(null);
      setDue("");
      await reload();
    });
  return (
    <Tile paper testId="new-task">
      <h2 class="title">{words.addTask}</h2>
      <Field name="task-what" label={words.taskWhat} value={what} onInput={setWhat} maxLength={80} />
      <p class="label">{words.who}</p>
      <PersonChoices people={people} chosen={who?.holder_person_id ?? null} onChoose={setWho} testId="task-who" />
      <Field name="task-due" label={words.taskDue} value={due} onInput={setDue} type="datetime-local" />
      <Pill plum onClick={() => void add()} disabled={act.busy || !who || !what.trim()} testId="add-task">
        {words.addTask}
      </Pill>
      <NoticeAt act={act} where="task" />
    </Tile>
  );
}
