"""Additional books for the Books section's "All books" view (the curated essentials stay in books.json).

Selection: widely cited and widely read books on American constitutional law, history and the Court, drawn from the
standard literature and cross-checked against OpenAlex citation counts and the law reviews in the article index.
Each entry is verified against Open Library by build_books.pl (title + author must match a real work, and Open
Library's first-publication year is used); entries that do not verify are dropped and listed.
Run:  python scripts/books_more.py   -> merges these into scripts/books.json as non-essential entries.
"""
import json, re

T, H, C, S, R, D, I = ('Theory & Interpretation', 'History & Founding', 'The Supreme Court', 'Structure & Powers',
                       'Rights & Liberties', 'Democracy & Elections', 'Introductions & Primers')
BOOKS = [
    # ---- theory & interpretation
    (T, 'American Constitutional Law', ['Laurence H. Tribe'], 1978), (T, 'On Reading the Constitution', ['Laurence H. Tribe', 'Michael C. Dorf'], 1991),
    (T, 'The Partial Constitution', ['Cass R. Sunstein'], 1993), (T, 'Radicals in Robes', ['Cass R. Sunstein'], 2005),
    (T, 'Legal Reasoning and Political Conflict', ['Cass R. Sunstein'], 1996), (T, 'How Judges Think', ['Richard A. Posner'], 2008),
    (T, 'Overcoming Law', ['Richard A. Posner'], 1995), (T, "Law's Empire", ['Ronald Dworkin'], 1986), (T, 'Law and Disagreement', ['Jeremy Waldron'], 1999),
    (T, 'The Dignity of Legislation', ['Jeremy Waldron'], 1999), (T, 'The Concept of Law', ['H. L. A. Hart'], 1961), (T, 'The Morality of Law', ['Lon L. Fuller'], 1964),
    (T, 'The Supreme Court and the Idea of Progress', ['Alexander M. Bickel'], 1970), (T, 'The Morality of Consent', ['Alexander M. Bickel'], 1975),
    (T, 'Constitutional Redemption', ['Jack M. Balkin'], 2011), (T, 'The Cycles of Constitutional Time', ['Jack M. Balkin'], 2020),
    (T, 'Constitutional Construction', ['Keith E. Whittington'], 1999), (T, 'Political Foundations of Judicial Supremacy', ['Keith E. Whittington'], 2007),
    (T, 'Our Republican Constitution', ['Randy E. Barnett'], 2016), (T, 'Originalism and the Good Constitution', ['John O. McGinnis', 'Michael B. Rappaport'], 2013),
    (T, 'Constitutional Originalism: A Debate', ['Robert W. Bennett', 'Lawrence B. Solum'], 2011), (T, 'Constitutional Interpretation', ['Philip Bobbitt'], 1991),
    (T, 'Constitutional Interpretation: The Basic Questions', ['Sotirios A. Barber', 'James E. Fleming'], 2007), (T, 'Judging Under Uncertainty', ['Adrian Vermeule'], 2006),
    (T, "Law's Abnegation", ['Adrian Vermeule'], 2016), (T, 'Red, White, and Blue: A Critical Analysis of Constitutional Law', ['Mark Tushnet'], 1988),
    (T, 'Weak Courts, Strong Rights', ['Mark Tushnet'], 2008), (T, 'Government by Judiciary', ['Raoul Berger'], 1977),
    (T, 'Constitutional Self-Government', ['Christopher L. Eisgruber'], 2001), (T, 'We the People, Volume 3: The Civil Rights Revolution', ['Bruce Ackerman'], 2014),
    (T, 'The Law of the Land', ['Akhil Reed Amar'], 2015), (T, 'Constitutional Faith', ['Sanford Levinson'], 1988), (T, 'Brennan and Democracy', ['Frank I. Michelman'], 1999),
    (T, 'Implementing the Constitution', ['Richard H. Fallon Jr.'], 2001), (T, 'Cosmic Constitutional Theory', ['J. Harvie Wilkinson III'], 2012),
    (T, 'We the People: A Progressive Reading of the Constitution for the Twenty-First Century', ['Erwin Chemerinsky'], 2018),
    (T, 'Originalism as Faith', ['Eric J. Segall'], 2018), (T, 'Against Constitutional Originalism', ['Jonathan Gienapp'], 2024),
    (T, 'Structure and Relationship in Constitutional Law', ['Charles L. Black Jr.'], 1969), (T, 'On Constitutional Disobedience', ['Louis Michael Seidman'], 2012),
    (T, 'The Second Bill of Rights', ['Cass R. Sunstein'], 2004), (T, 'Law and Judicial Duty', ['Philip Hamburger'], 2008),
    (T, 'The Constitution in Exile', ['Andrew P. Napolitano'], 2006), (T, 'Constitutional Rot', ['Jack M. Balkin'], 2024),
    (T, 'Taking Back the Constitution', ['Mark Tushnet'], 2020), (T, 'The Constitution of Liberty', ['Friedrich A. Hayek'], 1960),
    (T, 'Freedom and the Court', ['Henry J. Abraham'], 1967), (T, 'The Federalist Society: How Conservatives Took the Law Back from Liberals', ['Michael Avery', 'Danielle McLaughlin'], 2013),
    # ---- history & founding
    (H, 'The Framing of the Constitution of the United States', ['Max Farrand'], 1913), (H, 'The Records of the Federal Convention of 1787', ['Max Farrand'], 1911),
    (H, 'Notes of Debates in the Federal Convention of 1787', ['James Madison'], 1840), (H, 'What the Anti-Federalists Were For', ['Herbert J. Storing'], 1981),
    (H, 'The Radicalism of the American Revolution', ['Gordon S. Wood'], 1991), (H, 'Empire of Liberty', ['Gordon S. Wood'], 2009),
    (H, 'American Scripture', ['Pauline Maier'], 1997), (H, 'Founding Brothers', ['Joseph J. Ellis'], 2000), (H, 'The Quartet', ['Joseph J. Ellis'], 2015),
    (H, 'Plain, Honest Men', ['Richard Beeman'], 2009), (H, 'Novus Ordo Seclorum', ['Forrest McDonald'], 1985), (H, 'The Sacred Fire of Liberty', ['Lance Banning'], 1995),
    (H, 'Revolutionaries: A New History of the Invention of America', ['Jack N. Rakove'], 2010), (H, 'The Words That Made Us', ['Akhil Reed Amar'], 2021),
    (H, 'Our Declaration', ['Danielle Allen'], 2014), (H, "Reconstruction: America's Unfinished Revolution", ['Eric Foner'], 1988),
    (H, 'Democracy Reborn', ['Garrett Epps'], 2006), (H, 'No State Shall Abridge', ['Michael Kent Curtis'], 1986),
    (H, 'The Fourteenth Amendment: From Political Principle to Judicial Doctrine', ['William E. Nelson'], 1988),
    (H, 'The Constitution in the Supreme Court: The First Hundred Years', ['David P. Currie'], 1985), (H, 'The Constitution in Congress: The Federalist Period', ['David P. Currie'], 1997),
    (H, 'The Dred Scott Case', ['Don E. Fehrenbacher'], 1978), (H, 'Slavery and the Founders', ['Paul Finkelman'], 1996), (H, 'No Property in Man', ['Sean Wilentz'], 2018),
    (H, 'The Crooked Path to Abolition', ['James Oakes'], 2021), (H, "Madison's Hand", ['Mary Sarah Bilder'], 2015), (H, 'These Truths', ['Jill Lepore'], 2018),
    (H, 'Unruly Americans and the Origins of the Constitution', ['Woody Holton'], 2007), (H, 'A Brilliant Solution', ['Carol Berkin'], 2002),
    (H, 'Origins of the Fifth Amendment', ['Leonard W. Levy'], 1968), (H, 'Emergence of a Free Press', ['Leonard W. Levy'], 1985),
    (H, 'Separation of Church and State', ['Philip Hamburger'], 2002), (H, 'The Plessy Case', ['Charles A. Lofgren'], 1987), (H, 'Inventing the People', ['Edmund S. Morgan'], 1988),
    (H, 'Alexander Hamilton', ['Ron Chernow'], 2004), (H, 'The Other Founders', ['Saul Cornell'], 1999), (H, 'The Second Creation', ['Jonathan Gienapp'], 2018),
    (H, 'The Ideological Origins of American Federalism', ['Alison L. LaCroix'], 2010), (H, 'Until Justice Be Done', ['Kate Masur'], 2021),
    (H, 'A Legal History of the Civil War and Reconstruction', ['Laura F. Edwards'], 2015), (H, 'The Broken Constitution', ['Noah Feldman'], 2021),
    (H, 'The Federalist Papers', ['Alexander Hamilton', 'James Madison', 'John Jay'], 1788), (H, 'The Anti-Federalist Papers', ['Ralph Ketcham'], 1986),
    (H, 'Democracy in America', ['Alexis de Tocqueville'], 1835), (H, 'Commentaries on the Constitution of the United States', ['Joseph Story'], 1833),
    (H, 'The Day Freedom Died', ['Charles Lane'], 2008), (H, 'Separate: The Story of Plessy v. Ferguson', ['Steve Luxenberg'], 2019),
    (H, 'Birthright Citizens', ['Martha S. Jones'], 2018), (H, 'The Constitution: A Biography', ['Akhil Reed Amar'], 2005),
    (H, 'The Summer of 1787', ['David O. Stewart'], 2007), (H, 'Vanguard of the Revolution', ['Richard R. Beeman'], 2013),
    # ---- the Supreme Court
    (C, 'Justices, Presidents, and Senators', ['Henry J. Abraham'], 1974), (C, 'A History of the Supreme Court', ['Bernard Schwartz'], 1993),
    (C, 'The Warren Court and American Politics', ['Lucas A. Powe Jr.'], 2000), (C, 'The Supreme Court and the American Elite, 1789-2008', ['Lucas A. Powe Jr.'], 2009),
    (C, 'The Supreme Court', ['William H. Rehnquist'], 1987), (C, 'The Oath', ['Jeffrey Toobin'], 2012), (C, 'Supreme Conflict', ['Jan Crawford Greenburg'], 2007),
    (C, 'Becoming Justice Blackmun', ['Linda Greenhouse'], 2005), (C, 'The Chief: The Life and Turbulent Times of Chief Justice John Roberts', ['Joan Biskupic'], 2019),
    (C, "Sandra Day O'Connor", ['Joan Biskupic'], 2005), (C, 'Scorpions', ['Noah Feldman'], 2010), (C, 'John Marshall: Definer of a Nation', ['Jean Edward Smith'], 1996),
    (C, 'John Marshall and the Heroic Age of the Supreme Court', ['R. Kent Newmyer'], 2001), (C, 'Learned Hand: The Man and the Judge', ['Gerald Gunther'], 1994),
    (C, 'The American Judicial Tradition', ['G. Edward White'], 1976), (C, 'Justice Brennan: Liberal Champion', ['Seth Stern', 'Stephen Wermiel'], 2010),
    (C, 'Louis D. Brandeis: A Life', ['Melvin I. Urofsky'], 2009), (C, 'My Own Words', ['Ruth Bader Ginsburg'], 2016), (C, 'My Beloved World', ['Sonia Sotomayor'], 2013),
    (C, "My Grandfather's Son", ['Clarence Thomas'], 2007), (C, 'Five Chiefs', ['John Paul Stevens'], 2011), (C, 'Making Our Democracy Work', ['Stephen Breyer'], 2010),
    (C, 'The Supreme Court and the Attitudinal Model Revisited', ['Jeffrey A. Segal', 'Harold J. Spaeth'], 2002), (C, 'The Choices Justices Make', ['Lee Epstein', 'Jack Knight'], 1998),
    (C, 'The Behavior of Federal Judges', ['Lee Epstein', 'William M. Landes', 'Richard A. Posner'], 2013), (C, 'The Rights Revolution', ['Charles R. Epp'], 1998),
    (C, 'The Rise of the Conservative Legal Movement', ['Steven M. Teles'], 2008), (C, 'The Most Democratic Branch', ['Jeffrey Rosen'], 2006),
    (C, 'Supreme Inequality', ['Adam Cohen'], 2020), (C, 'Injustices', ['Ian Millhiser'], 2015), (C, 'In the Balance', ['Mark Tushnet'], 2013),
    (C, 'Uncertain Justice', ['Laurence Tribe', 'Joshua Matz'], 2014), (C, 'Storm Center', ['David M. O\'Brien'], 1986),
    (C, "A People's History of the Supreme Court", ['Peter Irons'], 1999), (C, 'The Oxford Companion to the Supreme Court of the United States', ['Kermit L. Hall'], 1992),
    (C, 'Making Civil Rights Law', ['Mark Tushnet'], 1994), (C, 'Thurgood Marshall: American Revolutionary', ['Juan Williams'], 1998),
    (C, 'Democratic Justice: Felix Frankfurter, the Supreme Court, and the Making of the Liberal Establishment', ['Brad Snyder'], 2022),
    (C, 'Ruth Bader Ginsburg: A Life', ['Jane Sherron De Hart'], 2018), (C, 'The Supreme Court in Conference', ['Del Dickson'], 2001),
    (C, 'Courtwatchers', ['Clare Cushman'], 2011), (C, 'Closed Chambers', ['Edward Lazarus'], 1998), (C, 'Nine Old Men', ['Drew Pearson', 'Robert S. Allen'], 1936),
    (C, 'Hugo Black: A Biography', ['Roger K. Newman'], 1994), (C, 'Earl Warren: A Public Life', ['G. Edward White'], 1982),
    (C, 'Super Chief: Earl Warren and His Supreme Court', ['Bernard Schwartz'], 1983), (C, 'The Majesty of the Law', ["Sandra Day O'Connor"], 2003),
    (C, 'Scalia: A Court of One', ['Bruce Allen Murphy'], 2014), (C, 'The Court and the World', ['Stephen Breyer'], 2015),
    (C, 'Deciding to Decide', ['H. W. Perry Jr.'], 1991), (C, 'The Supreme Court in the Early Republic', ['William R. Casto'], 1995),
    (C, 'Packing the Court', ['James MacGregor Burns'], 2009), (C, 'Supreme Power: Franklin Roosevelt vs. the Supreme Court', ['Jeff Shesol'], 2010),
    (C, 'The Supreme Court Reborn', ['William E. Leuchtenburg'], 1995), (C, 'Justice for All: Earl Warren and the Nation He Made', ['Jim Newton'], 2006),
    # ---- structure & powers
    (S, 'The President: Office and Powers', ['Edward S. Corwin'], 1940), (S, 'Presidential Power', ['Richard E. Neustadt'], 1960),
    (S, 'Constitutional Conflicts Between Congress and the President', ['Louis Fisher'], 1985), (S, 'The National Security Constitution', ['Harold Hongju Koh'], 1990),
    (S, 'The Powers of War and Peace', ['John Yoo'], 2005), (S, 'The Terror Presidency', ['Jack Goldsmith'], 2007), (S, 'Power and Constraint', ['Jack Goldsmith'], 2012),
    (S, 'The Decline and Fall of the American Republic', ['Bruce Ackerman'], 2010), (S, 'Imperial from the Beginning', ['Saikrishna Bangalore Prakash'], 2015),
    (S, 'The Living Presidency', ['Saikrishna Bangalore Prakash'], 2020), (S, "Congress's Constitution", ['Josh Chafetz'], 2017),
    (S, 'The Administrative Threat', ['Philip Hamburger'], 2017), (S, 'Creating the Administrative Constitution', ['Jerry L. Mashaw'], 2012),
    (S, "Tocqueville's Nightmare", ['Daniel R. Ernst'], 2014), (S, 'Impeachment: The Constitutional Problems', ['Raoul Berger'], 1973),
    (S, 'Impeachment: A Handbook', ['Charles L. Black Jr.'], 1974), (S, 'The Federal Impeachment Process', ['Michael J. Gerhardt'], 1996),
    (S, "Impeachment: A Citizen's Guide", ['Cass R. Sunstein'], 2017), (S, 'To End a Presidency', ['Laurence Tribe', 'Joshua Matz'], 2018),
    (S, 'Enhancing Government: Federalism for the 21st Century', ['Erwin Chemerinsky'], 2008), (S, 'The Upside-Down Constitution', ['Michael S. Greve'], 2012),
    (S, 'The Implosion of American Federalism', ['Robert F. Nagel'], 2001), (S, 'The Robust Federation', ['Jenna Bednar'], 2009),
    (S, 'Terror in the Balance', ['Eric A. Posner', 'Adrian Vermeule'], 2007), (S, "Madison's Nightmare", ['Peter M. Shane'], 2009),
    (S, 'The Politics Presidents Make', ['Stephen Skowronek'], 1993), (S, 'Power without Persuasion', ['William G. Howell'], 2003),
    (S, 'The Federal Courts and the Federal System', ['Henry M. Hart Jr.', 'Herbert Wechsler'], 1953), (S, 'Delegating Powers', ['David Epstein', "Sharyn O'Halloran"], 1999),
    (S, 'Building a New American State', ['Stephen Skowronek'], 1982), (S, 'Federalism: Origin, Operation, Significance', ['William H. Riker'], 1964),
    (S, 'Presidential War Power', ['Louis Fisher'], 1995), (S, 'The Constitution and the Conduct of Foreign Policy', ['Louis Henkin'], 1972),
    (S, 'Foreign Affairs and the United States Constitution', ['Louis Henkin'], 1996), (S, 'The Price of Federalism', ['Paul E. Peterson'], 1995),
    (S, 'The Unitary Executive', ['Steven G. Calabresi', 'Christopher S. Yoo'], 2008), (S, 'Separation of Powers and Good Government', ['Bradford P. Wilson'], 1994),
    (S, 'Executive Privilege: A Constitutional Myth', ['Raoul Berger'], 1974), (S, 'Unchecked and Unbalanced', ['Frederick A. O. Schwarz Jr.', 'Aziz Z. Huq'], 2007),
    (S, 'Lincoln and the Court', ['Brian McGinty'], 2008), (S, 'The Age of Deference', ['David Rudenstine'], 2016),
    # ---- rights & liberties
    (R, 'Free Speech in the United States', ['Zechariah Chafee Jr.'], 1941), (R, 'Free Speech: A Philosophical Enquiry', ['Frederick Schauer'], 1982),
    (R, 'Democracy and the Problem of Free Speech', ['Cass R. Sunstein'], 1993), (R, 'Constitutional Domains', ['Robert C. Post'], 1995),
    (R, 'The Soul of the First Amendment', ['Floyd Abrams'], 2017), (R, 'Hate: Why We Should Resist It with Free Speech, Not Censorship', ['Nadine Strossen'], 2018),
    (R, 'The Harm in Hate Speech', ['Jeremy Waldron'], 2012), (R, 'Free Speech in Its Forgotten Years', ['David M. Rabban'], 1997), (R, 'The Tolerant Society', ['Lee C. Bollinger'], 1986),
    (R, 'The System of Freedom of Expression', ['Thomas I. Emerson'], 1970), (R, 'Minnesota Rag', ['Fred W. Friendly'], 1981),
    (R, 'Foreordained Failure', ['Steven D. Smith'], 1995), (R, 'Religion and the Constitution', ['Kent Greenawalt'], 2006),
    (R, 'Religious Freedom and the Constitution', ['Christopher L. Eisgruber', 'Lawrence G. Sager'], 2007), (R, 'The Establishment Clause', ['Leonard W. Levy'], 1986),
    (R, 'Religion and the American Constitutional Experiment', ['John Witte Jr.'], 2000), (R, 'Defending American Religious Neutrality', ['Andrew Koppelman'], 2013),
    (R, 'The Godless Constitution', ['Isaac Kramnick', 'R. Laurence Moore'], 1996), (R, 'Race, Crime, and the Law', ['Randall Kennedy'], 1997),
    (R, 'Silent Covenants', ['Derrick Bell'], 2004), (R, 'The Color of Law', ['Richard Rothstein'], 2017), (R, 'The New Jim Crow', ['Michelle Alexander'], 2010),
    (R, 'Covering: The Hidden Assault on Our Civil Rights', ['Kenji Yoshino'], 2006), (R, 'Reasoning from Race', ['Serena Mayeri'], 2011), (R, 'Justice at War', ['Peter Irons'], 1983),
    (R, 'Critical Race Theory: The Key Writings That Formed the Movement', ['Kimberlé Crenshaw'], 1995), (R, 'Critical Race Theory: An Introduction', ['Richard Delgado', 'Jean Stefancic'], 2001),
    (R, 'For Discrimination: Race, Affirmative Action, and the Law', ['Randall Kennedy'], 2013), (R, 'The Schoolhouse Gate', ['Justin Driver'], 2018),
    (R, 'Unfinished Business: Racial Equality in American History', ['Michael J. Klarman'], 2007),
    (R, 'Brown v. Board of Education: A Civil Rights Milestone and Its Troubled Legacy', ['James T. Patterson'], 2001), (R, 'Liberty and Sexuality', ['David J. Garrow'], 1994),
    (R, 'Before Roe v. Wade', ['Linda Greenhouse', 'Reva B. Siegel'], 2010), (R, 'After Roe', ['Mary Ziegler'], 2015), (R, 'Dollars for Life', ['Mary Ziegler'], 2022),
    (R, 'From the Closet to the Altar', ['Michael J. Klarman'], 2012), (R, 'Love Wins', ['Debbie Cenziper', 'Jim Obergefell'], 2016), (R, 'Understanding Privacy', ['Daniel J. Solove'], 2008),
    (R, 'Speak Now: Marriage Equality on Trial', ['Kenji Yoshino'], 2015), (R, 'A Well-Regulated Militia', ['Saul Cornell'], 2006), (R, 'To Keep and Bear Arms', ['Joyce Lee Malcolm'], 1994),
    (R, 'That Every Man Be Armed', ['Stephen P. Halbrook'], 1984), (R, 'Chokehold', ['Paul Butler'], 2017), (R, 'Unwarranted: Policing Without Permission', ['Barry Friedman'], 2017),
    (R, 'Miranda: Crime, Law, and Politics', ['Liva Baker'], 1983), (R, 'The Death Penalty: An American History', ['Stuart Banner'], 2002), (R, 'Peculiar Institution', ['David Garland'], 2010),
    (R, 'Just Mercy', ['Bryan Stevenson'], 2014), (R, 'Charged', ['Emily Bazelon'], 2019), (R, 'Economic Liberties and the Constitution', ['Bernard H. Siegan'], 1980),
    (R, 'Rehabilitating Lochner', ['David E. Bernstein'], 2011), (R, 'The Constitution Besieged', ['Howard Gillman'], 1993), (R, 'The Grasping Hand', ['Ilya Somin'], 2015),
    (R, 'Little Pink House', ['Jeff Benedict'], 2009), (R, 'The Guardian of Every Other Right', ['James W. Ely Jr.'], 1992), (R, 'Shielded: How the Police Became Untouchable', ['Joanna Schwartz'], 2023),
    (R, 'Americans in Waiting', ['Hiroshi Motomura'], 2006), (R, 'Citizenship Without Consent', ['Peter H. Schuck', 'Rogers M. Smith'], 1985), (R, 'Civic Ideals', ['Rogers M. Smith'], 1997),
    (R, 'Feminism Unmodified', ['Catharine A. MacKinnon'], 1987), (R, 'Sexual Harassment of Working Women', ['Catharine A. MacKinnon'], 1979),
    (R, 'No Constitutional Right to Be Ladies', ['Linda K. Kerber'], 1998), (R, 'Enemy Aliens', ['David Cole'], 2003), (R, 'All the Laws but One', ['William H. Rehnquist'], 1998),
    (R, 'The Original Meaning of the Fourteenth Amendment', ['Randy E. Barnett', 'Evan D. Bernick'], 2021), (R, 'Privacy and Freedom', ['Alan F. Westin'], 1967),
    (R, 'The Alchemy of Race and Rights', ['Patricia J. Williams'], 1991), (R, 'Engines of Liberty', ['David Cole'], 2016), (R, 'Brown at 50', ['Derrick Bell'], 2004),
    (R, 'The Second Amendment: A Biography', ['Michael Waldman'], 2014), (R, 'Free Speech: A History from Socrates to Social Media', ['Jacob Mchangama'], 2022),
    (R, 'Kill All the Lawyers', ['Robert C. Post'], 2001), (R, 'The Fourth Amendment: Its History and Interpretation', ['Thomas K. Clancy'], 2008),
    (R, 'Equal Protection: Race and Gender', ['Kenneth L. Karst'], 1989), (R, 'Belonging to America', ['Kenneth L. Karst'], 1989),
    # ---- democracy & elections
    (D, 'The Voting Wars', ['Richard L. Hasen'], 2012), (D, 'Plutocrats United', ['Richard L. Hasen'], 2016), (D, 'Election Meltdown', ['Richard L. Hasen'], 2020),
    (D, 'The Law of Democracy', ['Samuel Issacharoff', 'Pamela S. Karlan', 'Richard H. Pildes'], 1998), (D, 'Give Us the Ballot', ['Ari Berman'], 2015),
    (D, 'One Person, No Vote', ['Carol Anderson'], 2018), (D, 'Colorblind Injustice', ['J. Morgan Kousser'], 1999), (D, 'The Tyranny of the Majority', ['Lani Guinier'], 1994),
    (D, 'Whose Votes Count?', ['Abigail M. Thernstrom'], 1987), (D, 'Citizens Divided', ['Robert C. Post'], 2014), (D, 'Corruption in America', ['Zephyr Teachout'], 2014),
    (D, 'Let the People Pick the President', ['Jesse Wegman'], 2020), (D, 'Why Do We Still Have the Electoral College?', ['Alexander Keyssar'], 2020),
    (D, 'How Democracies Die', ['Steven Levitsky', 'Daniel Ziblatt'], 2018), (D, 'How to Save a Constitutional Democracy', ['Tom Ginsburg', 'Aziz Z. Huq'], 2018),
    (D, 'How Democratic Is the American Constitution?', ['Robert A. Dahl'], 2001), (D, 'The Fight to Vote', ['Michael Waldman'], 2016),
    (D, 'Too Close to Call', ['Jeffrey Toobin'], 2001), (D, 'Supreme Injustice', ['Alan M. Dershowitz'], 2001), (D, 'Breaking the Deadlock', ['Richard A. Posner'], 2001),
    (D, 'Bush v. Gore: The Question of Legitimacy', ['Bruce Ackerman'], 2002), (D, 'The Semisovereign People', ['E. E. Schattschneider'], 1960),
    (D, 'Tyranny of the Minority', ['Steven Levitsky', 'Daniel Ziblatt'], 2023), (D, 'Ratf**ked', ['David Daley'], 2016),
    (D, 'Gerrymandering in America', ['Anthony J. McGann'], 2016), (D, 'Bending Toward Justice', ['Gary May'], 2013),
    (D, 'Quiet Revolution in the South', ['Chandler Davidson', 'Bernard Grofman'], 1994), (D, 'Democracy and Its Critics', ['Robert A. Dahl'], 1989),
    (D, 'The Unprecedented 2000 Election', ['Howard Gillman'], 2001), (D, 'Faithless Elector', ['Robert Alexander'], 2019),
    # ---- introductions & primers
    (I, 'The Dynamic Constitution', ['Richard H. Fallon Jr.'], 2004), (I, 'The Words We Live By', ['Linda R. Monk'], 2003),
    (I, 'The Constitution: An Introduction', ['Michael Stokes Paulsen', 'Luke Paulsen'], 2015), (I, 'The Annotated U.S. Constitution and Declaration of Independence', ['Jack N. Rakove'], 2009),
    (I, 'Constitutional Myths', ['Ray Raphael'], 2013), (I, 'The Heritage Guide to the Constitution', ['Edwin Meese III'], 2005),
    (I, 'Why the Constitution Matters', ['Mark Tushnet'], 2010), (I, 'Constitutional Law', ['John E. Nowak', 'Ronald D. Rotunda'], 1978),
    (I, 'The Supreme Court: A Very Short Introduction', ['Linda Greenhouse'], 2012), (I, 'The U.S. Constitution: A Very Short Introduction', ['David J. Bodenhamer'], 2018),
    (I, 'A More Perfect Constitution', ['Larry J. Sabato'], 2007), (I, 'The Constitution Today', ['Akhil Reed Amar'], 2016),
    (I, 'Constitutional Law: Principles and Policies', ['Erwin Chemerinsky'], 1997), (I, 'Understanding the Constitution', ['Jack W. Peltason'], 1949),
    (I, 'The American Supreme Court', ['Robert G. McCloskey'], 1960),
]
ESSENTIAL_ADDS = {'The American Supreme Court'}   # added to the essential set after review
MOVE_ESSENTIAL_CAT = {'The American Supreme Court': C}


def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', t.lower().split(':')[0]).strip('-')[:48]


def excluded():
    """ids listed in scripts/books_excluded.tsv (out of scope; see the reasons there)."""
    return {l.split('\t')[0] for l in open('scripts/books_excluded.tsv', encoding='utf-8') if l.strip() and not l.startswith('#')}


def main():
    books = json.load(open('scripts/books.json', encoding='utf-8'))
    ex = excluded()
    pruned = [b['title'] for b in books if b['id'] in ex]
    books = [b for b in books if b['id'] not in ex]
    have = {re.sub(r'[^a-z0-9]', '', b['title'].lower().split(':')[0]) for b in books}
    ids = {b['id'] for b in books}
    for b in books:
        b.setdefault('essential', True)
    added = 0
    for cat, title, authors, year in BOOKS:
        k = re.sub(r'[^a-z0-9]', '', title.lower().split(':')[0])
        if k in have:
            continue
        bid = slug(title)
        if bid in ex:
            continue
        while bid in ids:
            bid += '-2'
        have.add(k); ids.add(bid)
        books.append({'id': bid, 'title': title, 'authors': authors, 'year': year, 'cat': MOVE_ESSENTIAL_CAT.get(title, cat),
                      'essential': title in ESSENTIAL_ADDS})
        added += 1
    json.dump(books, open('scripts/books.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'books.json: {len(books)} books ({sum(b["essential"] for b in books)} essential); added {added}; removed {len(pruned)} excluded')


if __name__ == '__main__':
    main()
