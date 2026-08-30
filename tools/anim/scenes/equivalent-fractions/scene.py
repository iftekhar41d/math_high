from manim import *

class EquivalentFractionsScene(Scene):
    def construct(self):
        self.camera.background_color = "#F9F7F7"

        BG = "#F9F7F7"
        ACCENT = "#DBE2EF"
        PRIMARY = "#3F72AF"
        DARK = "#112D4E"

        # ---------- Title ----------
        title = Tex("Equivalent Fractions", color=DARK).scale(1.3)
        title.to_edge(UP, buff=0.6)
        self.play(Write(title))
        self.wait(0.5)

        def make_bar(total, shaded, width=8, height=1.2):
            group = VGroup()
            part_width = width / total
            for i in range(total):
                color = PRIMARY if i < shaded else ACCENT
                rect = Rectangle(
                    width=part_width,
                    height=height,
                    fill_color=color,
                    fill_opacity=1,
                    stroke_color=DARK,
                    stroke_width=2,
                )
                rect.move_to(LEFT * width / 2 + RIGHT * (i + 0.5) * part_width)
                group.add(rect)
            group.move_to(ORIGIN)
            return group

        # ---------- Step 1: 1/2 ----------
        bar1 = make_bar(2, 1)
        bar1.move_to(UP * 0.5)
        label1 = MathTex(r"\frac{1}{2}", color=DARK).scale(1.4)
        label1.next_to(bar1, DOWN, buff=0.5)

        self.play(FadeIn(bar1))
        self.play(Write(label1))
        self.wait(1)

        # ---------- Step 2: 2/4 ----------
        bar2 = make_bar(4, 2)
        bar2.move_to(UP * 0.5)
        label2 = MathTex(r"\frac{2}{4}", color=DARK).scale(1.4)
        label2.next_to(bar2, DOWN, buff=0.5)

        self.play(ReplacementTransform(bar1, bar2), ReplacementTransform(label1, label2))
        self.wait(1)

        # ---------- Step 3: 3/6 ----------
        bar3 = make_bar(6, 3)
        bar3.move_to(UP * 0.5)
        label3 = MathTex(r"\frac{3}{6}", color=DARK).scale(1.4)
        label3.next_to(bar3, DOWN, buff=0.5)

        self.play(ReplacementTransform(bar2, bar3), ReplacementTransform(label2, label3))
        self.wait(0.5)

        chain = MathTex(
            r"\frac{1}{2}", "=", r"\frac{2}{4}", "=", r"\frac{3}{6}", color=DARK
        ).scale(1.1)
        chain.next_to(bar3, DOWN, buff=1.0)

        self.play(FadeOut(label3), Write(chain))
        self.wait(1.5)

        # ---------- Step 4: the rule ----------
        self.play(FadeOut(bar3), FadeOut(chain), FadeOut(title))

        rule_title = Tex("Multiply top and bottom by the same number", color=DARK).scale(0.9)
        rule_title.to_edge(UP, buff=0.8)
        self.play(Write(rule_title))

        eq = MathTex(
            r"\frac{1}{2}", r"=", r"\frac{1 \times 3}{2 \times 3}", r"=", r"\frac{3}{6}",
            color=DARK
        ).scale(1.3)
        eq.move_to(UP * 0.3)

        self.play(Write(eq))
        self.wait(1)

        note = MathTex(r"\frac{3}{3} = 1", color=PRIMARY).scale(1.2)
        note.next_to(eq, DOWN, buff=0.8)
        note_text = Tex("Multiplying by 1 does not change the value", color=DARK).scale(0.8)
        note_text.next_to(note, DOWN, buff=0.4)

        self.play(Write(note))
        self.play(Write(note_text))
        self.wait(1.5)

        self.play(FadeOut(eq), FadeOut(note), FadeOut(note_text), FadeOut(rule_title))

        # ---------- Ending ----------
        final_text = Tex("Same amount, different names", color=DARK).scale(1.3)
        self.play(Write(final_text))
        self.wait(1)
