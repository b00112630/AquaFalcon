# Water rocket physics - short notes for the chatbot

## Newton's Third Law and thrust
For every action there is an equal and opposite reaction. Compressed air pushes the water
out of the nozzle downward at high speed (action); the water pushes the rocket upward/forward
(reaction). That push is called thrust. Thrust lasts only a fraction of a second, until the
water runs out; after that the rocket coasts.

## Newton's Second Law
F = m x a. The net force (thrust minus weight minus drag) divided by the mass gives the
acceleration. A lighter rocket accelerates more for the same thrust. As water leaves, the
rocket gets lighter, so it speeds up even faster during the thrust phase.

## Pressure
Pressure = force / area. The pump forces extra air into the bottle, raising the pressure
inside above atmospheric pressure (about 14.7 psi / 1 bar). Higher pressure = stronger,
longer thrust, but every bottle has a safe limit, so pressure must be controlled with a gauge.
1 bar is about 14.5 psi. 60 psi is about 4.1 bar.

## Why the water volume matters
Water is the "reaction mass" that gets thrown out. Air is the "spring" that stores energy.
- Too little water: very little mass is pushed out, so thrust is short and weak.
- Too much water: little room left for compressed air, and the rocket is heavy.
- Around one-third full is the classic sweet spot, but each rocket should be tested.

## Stability: centre of gravity (CG) and centre of pressure (CP)
- CG: the balance point of the rocket's mass.
- CP: the point where aerodynamic forces act (it depends on the shape; fins move it backward).
- A rocket is stable when the CG is ahead of (closer to the nose than) the CP, ideally by about
  1 to 2 body diameters. Then air pushes the tail back into line like a weather vane / dart.
- Adding weight to the nose moves the CG forward. Bigger or further-back fins move the CP back.
- If the CG is behind the CP, the rocket tumbles or loops.
- Quick checks: balance the rocket on a finger to find the CG; the swing test (tie a string at
  the CG and swing it in a circle - a stable rocket points nose-first).

## Projectile motion
After the thrust ends, the rocket is a projectile: gravity (g = 9.81 m/s^2) pulls it down while
it keeps moving forward. Without air resistance the path is a parabola and the range is
R = v^2 x sin(2 x angle) / g, so 45 degrees gives the maximum range in theory. With real air
resistance the best angle is often slightly lower (around 40-45 degrees).
The horizontal and vertical motions are independent: horizontal speed stays roughly constant
(ignoring drag), vertical speed decreases on the way up and increases on the way down.

## Drag (air resistance)
Air pushes against the moving rocket. A smooth, pointed nose cone and neat, thin fins reduce
drag. Drag grows quickly with speed (roughly with speed squared).

## Energy
The pump does work on the air, storing potential energy as pressure. On launch this becomes
kinetic energy of the water and the rocket, then gravitational potential energy as it climbs.

## Engineering design process
Define the problem -> research -> brainstorm -> design -> build a prototype -> test ->
analyse the data -> improve -> repeat.  Our launches are the "test and improve" loop.
